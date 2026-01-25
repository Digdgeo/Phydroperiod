"""
Core functions for hydroperiod calculation.

Hydroperiod represents the number of days a pixel remains flooded
during a hydrological cycle (September 1st - August 31st).
"""

import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import rasterio
from rasterio.profiles import Profile


def calculate_scene_weights(
    mask_files: List[str],
    hydrological_year_start: Tuple[int, int] = (9, 1),
) -> Dict[str, Dict[str, float]]:
    """Calculate the weight in days for each scene within a hydrological cycle.

    Distributes 365 days among available scenes, assigning each one
    a day range proportional to its temporal position.

    Args:
        mask_files: List of paths to mask files. Filenames must
            start with YYYYMMDD format (e.g., 20200315_flood.tif).
        hydrological_year_start: Tuple (month, day) of the hydrological
            cycle start. Default (9, 1) = September 1st.

    Returns:
        Dictionary {scene_date: {'weight': days, 'start': start_day, 'end': end_day}}.

    Example:
        >>> files = ["20200915_flood.tif", "20201015_flood.tif", "20201115_flood.tif"]
        >>> weights = calculate_scene_weights(files)
        >>> print(weights['20200915'])
        {'weight': 30.0, 'start': 0, 'end': 30.0}
    """
    # Extract dates from filenames
    scene_dates = []
    for f in mask_files:
        basename = os.path.basename(f)
        date_str = basename[:8]
        scene_dates.append(date_str)

    scene_dates = sorted(set(scene_dates))

    if not scene_dates:
        return {}

    # Determine base year of hydrological cycle
    years = [int(d[:4]) for d in scene_dates]
    base_year = min(years)
    start_month, start_day = hydrological_year_start
    d0 = date(base_year, start_month, start_day)

    # Calculate days from cycle start for each scene
    days_from_start = []
    for date_str in scene_dates:
        year = int(date_str[:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
        d1 = date(year, month, day)
        delta = d1 - d0
        days_from_start.append(delta.days)

    # Calculate midpoints between consecutive scenes
    midpoints = []
    for i in range(len(days_from_start) - 1):
        mid = (days_from_start[i + 1] - days_from_start[i]) / 2
        midpoints.append(mid)

    # Calculate accumulated cutpoints
    cutpoints = []
    for i, mid in enumerate(midpoints):
        cutpoints.append(mid + days_from_start[i])

    # Calculate value (days) and ranges for each scene
    values = []
    ranges = []
    if cutpoints:
        # First scene: from 0 to first cutpoint
        values.append(cutpoints[0])
        ranges.append((0, cutpoints[0]))
        # Middle scenes
        for i in range(len(cutpoints) - 1):
            values.append(cutpoints[i + 1] - cutpoints[i])
            ranges.append((cutpoints[i], cutpoints[i + 1]))
        # Last scene: from last cutpoint to 365 (exclusive, so includes up to day 364)
        values.append(365 - cutpoints[-1])
        ranges.append((cutpoints[-1], 365))
    else:
        # Single scene, assign 365 days
        values.append(365)
        ranges.append((0, 365))

    # Build result dictionary with weight and range info
    result = {}
    for i, scene_date in enumerate(scene_dates):
        result[scene_date] = {
            'weight': values[i],
            'start': ranges[i][0],
            'end': ranges[i][1],
        }

    return result


def process_masks(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    weights: Optional[Dict[str, float]] = None,
    water_value: int = 1,
    dry_value: int = 0,
    nodata_value: int = 2,
) -> Path:
    """Process water masks generating intermediate products per scene.

    For each mask generates three products:
    - *_flood_rec.tif: Flood days (pixels with water_value)
    - *_dry_rec.tif: Dry days (pixels with dry_value)
    - *_valid_rec.tif: Valid days (flood + dry, excluding nodata)

    Args:
        input_path: Directory containing water masks (.tif).
        output_path: Output directory. If not specified,
            creates an 'output' subdirectory in input_path.
        weights: Dictionary of weights per scene. If not specified,
            calculated automatically.
        water_value: Value representing water/flood in masks.
            Default 1.
        dry_value: Value representing dry land in masks.
            Default 0.
        nodata_value: Value representing nodata (clouds, shadows, etc.).
            Default 2. These pixels are excluded from calculation.

    Returns:
        Path to output directory with intermediate products.
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path / "output"
    else:
        output_path = Path(output_path)

    output_path.mkdir(parents=True, exist_ok=True)

    # Get list of masks (only files starting with YYYYMMDD pattern)
    mask_files = sorted([
        f for f in input_path.glob("*.tif")
        if f.name[:8].isdigit()
    ])

    if not mask_files:
        raise ValueError(f"No .tif files found in {input_path}")

    # Calculate weights if not provided
    if weights is None:
        weights = calculate_scene_weights([str(f) for f in mask_files])

    # Process each mask
    for mask_file in mask_files:
        date_str = mask_file.name[:8]
        scene_info = weights.get(date_str, {})
        weight = scene_info.get('weight', 0) if isinstance(scene_info, dict) else scene_info

        if weight == 0:
            continue

        with rasterio.open(mask_file) as src:
            data = src.read()
            profile = src.profile.copy()
            profile.update(dtype=rasterio.float32)

            # Flooded: where pixel = water_value, assign weight
            flood_data = np.where(data == water_value, weight, 0).astype(np.float32)

            # Dry: where pixel = dry_value, assign weight
            dry_data = np.where(data == dry_value, weight, 0).astype(np.float32)

            # Valid: sum of flood + dry (nodata is automatically excluded)
            valid_data = (flood_data + dry_data).astype(np.float32)

            # Save products
            base_name = mask_file.stem
            _write_raster(output_path / f"{base_name}_flood_rec.tif", flood_data, profile)
            _write_raster(output_path / f"{base_name}_dry_rec.tif", dry_data, profile)
            _write_raster(output_path / f"{base_name}_valid_rec.tif", valid_data, profile)

    return output_path


def accumulate_hydroperiod(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
) -> Tuple[Path, Path]:
    """Accumulate intermediate products to generate total hydroperiod.

    Sums all *_flood_rec.tif and *_valid_rec.tif to generate:
    - hydroperiod_YYYY_YYYY+1.tif: Total flood days
    - valid_days_YYYY_YYYY+1.tif: Total valid days

    Args:
        input_path: Directory with intermediate products (*_flood_rec.tif, *_valid_rec.tif).
        output_path: Output directory. If not specified, uses input_path's parent.

    Returns:
        Tuple (hydroperiod_path, valid_days_path).
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.parent
    else:
        output_path = Path(output_path)

    output_path.mkdir(parents=True, exist_ok=True)

    # Get files
    flood_files = sorted(input_path.glob("*_flood_rec.tif"))
    valid_files = sorted(input_path.glob("*_valid_rec.tif"))

    if not flood_files:
        raise ValueError(f"No *_flood_rec.tif files found in {input_path}")

    # Determine hydrological cycle
    first_file = flood_files[0].name
    year1 = first_file[:4]
    year2 = str(int(year1) + 1)
    cycle_suffix = f"_{year1}_{year2}"

    # Read first file to get shape and metadata
    with rasterio.open(flood_files[0]) as src:
        shape = src.read().shape
        profile = src.profile.copy()
        profile.update(dtype=rasterio.float32)

    # Accumulate flood
    flood_sum = np.zeros(shape, dtype=np.float32)
    for f in flood_files:
        with rasterio.open(f) as src:
            flood_sum += src.read()

    # Accumulate valid
    valid_sum = np.zeros(shape, dtype=np.float32)
    for f in valid_files:
        with rasterio.open(f) as src:
            valid_sum += src.read()

    # Save results as integers (days don't have decimals)
    hydroperiod_path = output_path / f"hydroperiod{cycle_suffix}.tif"
    valid_days_path = output_path / f"valid_days{cycle_suffix}.tif"

    profile.update(dtype=rasterio.int16, nodata=-1)
    with rasterio.open(hydroperiod_path, "w", **profile) as dst:
        dst.write(np.round(flood_sum).astype(np.int16))
    with rasterio.open(valid_days_path, "w", **profile) as dst:
        dst.write(np.round(valid_sum).astype(np.int16))

    return hydroperiod_path, valid_days_path


def _doy_to_date_int(doy: np.ndarray, base_year: int) -> np.ndarray:
    """Convert day of hydrological year (0-365/366) to YYYYMMDD integer format.

    Args:
        doy: Array of days since September 1st (0-365/366, where 0=Sep 1).
            Values beyond Aug 31 are capped to Aug 31 (last day of cycle).
        base_year: The starting year of the hydrological cycle

    Returns:
        Array with dates as integers (e.g., 20240915, 20250213)
    """
    from datetime import timedelta

    result = np.full_like(doy, -1, dtype=np.int32)
    d0 = date(base_year, 9, 1)

    # Calculate last day of cycle (Aug 31 of next year) accounting for leap years
    end_of_cycle = date(base_year + 1, 8, 31)
    max_doy = (end_of_cycle - d0).days  # 364 for normal years, 365 for leap years

    # Get unique valid days to avoid computing the same date multiple times
    valid_mask = doy >= 0
    unique_days = np.unique(doy[valid_mask])

    for day_val in unique_days:
        # Cap to max_doy (Aug 31) so DOY doesn't overflow to next cycle
        capped_day = min(int(day_val), max_doy)
        target_date = d0 + timedelta(days=capped_day)
        date_int = target_date.year * 10000 + target_date.month * 100 + target_date.day
        result[doy == day_val] = date_int

    return result


def calculate_first_last_flood(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    weights: Optional[Dict[str, Dict[str, float]]] = None,
    water_value: int = 1,
) -> Dict[str, Path]:
    """Calculate first and last flood day for each pixel.

    For each pixel, determines:
    - First flood day: the start of the range of the first scene where the pixel is flooded
    - Last flood day: the end of the range of the last scene where the pixel is flooded

    Generates both DOY (day of year, 0-365) and date (YYYYMMDD) formats.

    Args:
        input_path: Directory containing water masks (.tif).
        output_path: Output directory. If not specified, uses input_path.
        weights: Dictionary with scene info including 'start' and 'end' ranges.
            If not specified, calculated automatically.
        water_value: Value representing water/flood in masks. Default 1.

    Returns:
        Dictionary with paths:
        - 'first_flood_doy': First flood day as DOY (0-365)
        - 'last_flood_doy': Last flood day as DOY (0-365)
        - 'first_flood_date': First flood day as YYYYMMDD
        - 'last_flood_date': Last flood day as YYYYMMDD
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path
    else:
        output_path = Path(output_path)

    output_path.mkdir(parents=True, exist_ok=True)

    # Get list of masks (only files starting with YYYYMMDD pattern)
    mask_files = sorted([
        f for f in input_path.glob("*.tif")
        if f.name[:8].isdigit()
    ])

    if not mask_files:
        raise ValueError(f"No .tif files found in {input_path}")

    # Calculate weights if not provided
    if weights is None:
        weights = calculate_scene_weights([str(f) for f in mask_files])

    # Determine hydrological cycle
    first_file = mask_files[0].name
    year1 = int(first_file[:4])
    year2 = year1 + 1
    cycle_suffix = f"_{year1}_{year2}"

    # Read first file to get shape and metadata
    with rasterio.open(mask_files[0]) as src:
        shape = src.read().shape
        profile = src.profile.copy()

    # Initialize arrays (use -1 as nodata for "never flooded")
    first_flood = np.full(shape, -1, dtype=np.int16)
    last_flood = np.full(shape, -1, dtype=np.int16)

    # Process each mask in chronological order
    for mask_file in mask_files:
        date_str = mask_file.name[:8]
        scene_info = weights.get(date_str, {})

        if not scene_info:
            continue

        start_day = int(round(scene_info['start']))
        end_day = int(round(scene_info['end']))

        with rasterio.open(mask_file) as src:
            data = src.read()
            is_flooded = data == water_value

            # First flood: only update where not yet set (-1) and currently flooded
            first_flood = np.where(
                (first_flood == -1) & is_flooded,
                start_day,
                first_flood
            ).astype(np.int16)

            # Last flood: always update where flooded (will keep the last one)
            last_flood = np.where(is_flooded, end_day, last_flood).astype(np.int16)

    # Convert DOY to date format
    first_flood_date = _doy_to_date_int(first_flood, year1)
    last_flood_date = _doy_to_date_int(last_flood, year1)

    # Save DOY results (int16)
    profile_int16 = profile.copy()
    profile_int16.update(dtype=rasterio.int16, nodata=-1)

    first_flood_doy_path = output_path / f"first_flood_doy{cycle_suffix}.tif"
    last_flood_doy_path = output_path / f"last_flood_doy{cycle_suffix}.tif"

    with rasterio.open(first_flood_doy_path, "w", **profile_int16) as dst:
        dst.write(first_flood)
    with rasterio.open(last_flood_doy_path, "w", **profile_int16) as dst:
        dst.write(last_flood)

    # Save date results (int32 for YYYYMMDD format)
    profile_int32 = profile.copy()
    profile_int32.update(dtype=rasterio.int32, nodata=-1)

    first_flood_date_path = output_path / f"first_flood_date{cycle_suffix}.tif"
    last_flood_date_path = output_path / f"last_flood_date{cycle_suffix}.tif"

    with rasterio.open(first_flood_date_path, "w", **profile_int32) as dst:
        dst.write(first_flood_date)
    with rasterio.open(last_flood_date_path, "w", **profile_int32) as dst:
        dst.write(last_flood_date)

    return {
        'first_flood_doy': first_flood_doy_path,
        'last_flood_doy': last_flood_doy_path,
        'first_flood_date': first_flood_date_path,
        'last_flood_date': last_flood_date_path,
    }


def calculate_temporal_representativity(
    mask_files: List[str],
    hydrological_year_start: Tuple[int, int] = (9, 1),
    n_periods: int = 12,
) -> float:
    """Calculate Temporal Representativity Index (IRT).

    Measures how well distributed the observations are throughout the year.
    Returns a value from 0 to 1, where:
    - 1 = observations perfectly distributed across all periods
    - 0 = all observations concentrated in a single period

    The index is based on the Gini coefficient (inverted, so higher = better).

    Args:
        mask_files: List of paths to mask files with YYYYMMDD format.
        hydrological_year_start: Tuple (month, day) of cycle start.
        n_periods: Number of periods to divide the year into (default 12 = monthly).

    Returns:
        IRT value between 0 and 1.
    """
    # Extract dates from filenames
    scene_dates = []
    for f in mask_files:
        basename = os.path.basename(f)
        date_str = basename[:8]
        scene_dates.append(date_str)

    scene_dates = sorted(set(scene_dates))

    if not scene_dates:
        return 0.0

    # Determine base year
    years = [int(d[:4]) for d in scene_dates]
    base_year = min(years)
    start_month, start_day = hydrological_year_start
    d0 = date(base_year, start_month, start_day)

    # Calculate day of year for each scene (within hydrological cycle)
    days_in_cycle = []
    for date_str in scene_dates:
        year = int(date_str[:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
        d1 = date(year, month, day)
        delta = (d1 - d0).days % 365
        days_in_cycle.append(delta)

    # Count observations per period
    period_length = 365 / n_periods
    period_counts = np.zeros(n_periods)
    for day in days_in_cycle:
        period_idx = min(int(day / period_length), n_periods - 1)
        period_counts[period_idx] += 1

    # Calculate Gini coefficient
    # Sort counts
    sorted_counts = np.sort(period_counts)
    n = len(sorted_counts)
    cumsum = np.cumsum(sorted_counts)
    total = cumsum[-1]

    if total == 0:
        return 0.0

    # Gini = 1 - 2 * (area under Lorenz curve)
    # Area under Lorenz = sum of (cumsum / total) / n
    gini = 1 - 2 * np.sum(cumsum) / (n * total) + 1 / n

    # IRT = 1 - Gini (so higher = more uniform distribution)
    irt = 1 - gini

    return round(irt, 4)


def calculate_pixel_irt(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    nodata_value: int = 2,
    n_periods: int = 12,
    hydrological_year_start: Tuple[int, int] = (9, 1),
) -> Path:
    """Calculate Temporal Representativity Index (IRT) per pixel.

    For each pixel, measures how well distributed its valid observations are
    throughout the hydrological year. Pixels with nodata in certain scenes
    will have different IRT values.

    Returns a raster with values from 0 to 1, where:
    - 1 = observations perfectly distributed across all periods
    - 0 = all observations concentrated in a single period
    - -1 = nodata (pixel has no valid observations)

    Args:
        input_path: Directory containing water masks (.tif).
        output_path: Output directory. If not specified, uses input_path.
        nodata_value: Value representing nodata in masks. Default 2.
        n_periods: Number of periods to divide the year into (default 12 = monthly).
        hydrological_year_start: Tuple (month, day) of cycle start.

    Returns:
        Path to IRT raster.
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path
    else:
        output_path = Path(output_path)

    output_path.mkdir(parents=True, exist_ok=True)

    # Get list of masks (only files starting with YYYYMMDD pattern)
    mask_files = sorted([
        f for f in input_path.glob("*.tif")
        if f.name[:8].isdigit()
    ])

    if not mask_files:
        raise ValueError(f"No .tif files found in {input_path}")

    # Determine hydrological cycle and base year
    first_file = mask_files[0].name
    year1 = int(first_file[:4])
    year2 = year1 + 1
    cycle_suffix = f"_{year1}_{year2}"

    start_month, start_day = hydrological_year_start
    d0 = date(year1, start_month, start_day)

    # Calculate which period each scene belongs to
    period_length = 365 / n_periods
    scene_periods = {}
    for mask_file in mask_files:
        date_str = mask_file.name[:8]
        year = int(date_str[:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
        d1 = date(year, month, day)
        doy = (d1 - d0).days % 365
        period_idx = min(int(doy / period_length), n_periods - 1)
        scene_periods[str(mask_file)] = period_idx

    # Read first file to get shape and metadata
    with rasterio.open(mask_files[0]) as src:
        shape = src.read().shape
        profile = src.profile.copy()

    # Count observations per period for each pixel
    # Shape: (n_periods, bands, height, width)
    period_counts = np.zeros((n_periods,) + shape, dtype=np.float32)

    for mask_file in mask_files:
        period_idx = scene_periods[str(mask_file)]

        with rasterio.open(mask_file) as src:
            data = src.read()
            # Valid pixels (not nodata)
            is_valid = data != nodata_value
            period_counts[period_idx] += is_valid.astype(np.float32)

    # Calculate IRT for each pixel using vectorized Gini coefficient
    # Total observations per pixel
    total_obs = np.sum(period_counts, axis=0)

    # Initialize IRT with nodata
    irt = np.full(shape, -1, dtype=np.float32)

    # Only calculate for pixels with observations
    valid_pixels = total_obs > 0

    # Sort period counts along period axis
    sorted_counts = np.sort(period_counts, axis=0)

    # Calculate cumulative sum
    cumsum = np.cumsum(sorted_counts, axis=0)

    # Gini coefficient calculation (vectorized)
    # gini = 1 - 2 * sum(cumsum) / (n * total) + 1/n
    sum_cumsum = np.sum(cumsum, axis=0)

    with np.errstate(divide='ignore', invalid='ignore'):
        gini = 1 - 2 * sum_cumsum / (n_periods * total_obs) + 1 / n_periods
        # IRT = 1 - Gini
        irt_values = 1 - gini
        irt_values = np.where(np.isfinite(irt_values), irt_values, -1)

    irt = np.where(valid_pixels, irt_values, -1).astype(np.float32)

    # Save result
    irt_path = output_path / f"irt{cycle_suffix}.tif"
    profile.update(dtype=rasterio.float32, nodata=-1)
    with rasterio.open(irt_path, "w", **profile) as dst:
        dst.write(irt)

    return irt_path


def normalize_hydroperiod(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    target_days: int = 365,
) -> Path:
    """Normalize hydroperiod to a target number of days.

    Calculates: normalized_hydroperiod = (hydroperiod / valid_days) * target_days

    Args:
        input_path: Directory with hydroperiod_*.tif and valid_days_*.tif.
        output_path: Output directory. If not specified, uses input_path.
        target_days: Target days for normalization (default 365).

    Returns:
        Path to normalized file.
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path
    else:
        output_path = Path(output_path)

    output_path.mkdir(parents=True, exist_ok=True)

    # Find hydroperiod and valid_days files
    hydroperiod_file = None
    valid_days_file = None
    cycle = None

    for f in input_path.iterdir():
        if f.name.startswith("hydroperiod") and f.suffix == ".tif" and "nor" not in f.name:
            hydroperiod_file = f
            # Extract cycle from filename
            parts = f.stem.split("_")
            if len(parts) >= 3:
                cycle = f"{parts[1]}_{parts[2]}"
        elif f.name.startswith("valid_days") and f.suffix == ".tif":
            valid_days_file = f

    if hydroperiod_file is None or valid_days_file is None:
        raise ValueError(
            f"hydroperiod_*.tif and valid_days_*.tif files not found in {input_path}"
        )

    with rasterio.open(hydroperiod_file) as hyd_src:
        hyd_data = hyd_src.read()
        profile = hyd_src.profile.copy()

        with rasterio.open(valid_days_file) as val_src:
            val_data = val_src.read()

            # Normalize avoiding division by zero
            with np.errstate(divide="ignore", invalid="ignore"):
                normalized = np.true_divide(hyd_data, val_data) * target_days
                normalized = np.where(np.isfinite(normalized), normalized, 0)
                # Round to nearest integer (no decimal flood days)
                normalized = np.clip(np.round(normalized), 0, target_days).astype(np.int16)

    output_file = output_path / f"hydroperiod_nor_{cycle}.tif"
    profile.update(dtype=rasterio.int16, nodata=-1)
    with rasterio.open(output_file, "w", **profile) as dst:
        dst.write(normalized)

    return output_file


def compute_hydroperiod(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    normalize: bool = True,
    target_days: int = 365,
    water_value: int = 1,
    dry_value: int = 0,
    nodata_value: int = 2,
    compute_first_last: bool = True,
    compute_irt: bool = True,
) -> Dict[str, Union[Path, float]]:
    """Complete pipeline to calculate hydroperiod.

    Executes all calculation steps:
    1. Calculate weights per scene
    2. Process masks generating intermediate products
    3. Accumulate total hydroperiod
    4. (Optional) Normalize to target days
    5. (Optional) Calculate first/last flood day
    6. (Optional) Calculate Temporal Representativity Index (IRT)

    Args:
        input_path: Directory with water masks (.tif).
            Filenames with YYYYMMDD*.tif format.
        output_path: Base output directory. If not specified,
            subdirectories are created in input_path.
        normalize: If True, also generates normalized hydroperiod (as integers).
        target_days: Target days for normalization.
        water_value: Value representing water/flood in masks.
            Default 1.
        dry_value: Value representing dry land in masks.
            Default 0.
        nodata_value: Value representing nodata (clouds, shadows, etc.).
            Default 2. These pixels are excluded from calculation.
        compute_first_last: If True, generates first/last flood day rasters.
        compute_irt: If True, calculates the Temporal Representativity Index.

    Returns:
        Dictionary with paths to generated products:
        - 'intermediate_dir': directory with intermediate products
        - 'hydroperiod': path to accumulated hydroperiod
        - 'valid_days': path to accumulated valid days
        - 'normalized': path to normalized hydroperiod (if normalize=True)
        - 'first_flood': path to first flood day raster (if compute_first_last=True)
        - 'last_flood': path to last flood day raster (if compute_first_last=True)
        - 'irt': Temporal Representativity Index value (if compute_irt=True)

    Example:
        >>> results = compute_hydroperiod("/path/to/masks")
        >>> print(f"Hydroperiod: {results['hydroperiod']}")
        >>> print(f"IRT: {results['irt']}")
        Hydroperiod: /path/to/masks/hydroperiod_2020_2021.tif
        IRT: 0.85
    """
    input_path = Path(input_path)

    if output_path is None:
        intermediate_path = input_path / "output"
        final_path = input_path
    else:
        output_path = Path(output_path)
        intermediate_path = output_path / "intermediate"
        final_path = output_path

    # Get mask files for weight calculation (only files starting with YYYYMMDD pattern)
    mask_files = sorted([
        str(f) for f in input_path.glob("*.tif")
        if f.name[:8].isdigit()
    ])

    # Step 1: Calculate weights with ranges
    weights = calculate_scene_weights(mask_files)

    # Step 2: Process masks
    intermediate_dir = process_masks(
        input_path,
        intermediate_path,
        weights=weights,
        water_value=water_value,
        dry_value=dry_value,
        nodata_value=nodata_value,
    )

    # Step 3: Accumulate hydroperiod
    hydroperiod_path, valid_days_path = accumulate_hydroperiod(
        intermediate_dir, final_path
    )

    results = {
        "intermediate_dir": intermediate_dir,
        "hydroperiod": hydroperiod_path,
        "valid_days": valid_days_path,
    }

    # Step 4: Normalize (optional)
    if normalize:
        normalized_path = normalize_hydroperiod(final_path, final_path, target_days)
        results["normalized"] = normalized_path

    # Step 5: First/Last flood day (optional)
    if compute_first_last:
        flood_dates = calculate_first_last_flood(
            input_path, final_path, weights=weights, water_value=water_value
        )
        results["first_flood_doy"] = flood_dates['first_flood_doy']
        results["last_flood_doy"] = flood_dates['last_flood_doy']
        results["first_flood_date"] = flood_dates['first_flood_date']
        results["last_flood_date"] = flood_dates['last_flood_date']

    # Step 6: Calculate IRT (optional)
    if compute_irt:
        # Global IRT (for the scene collection)
        irt_global = calculate_temporal_representativity(mask_files)
        results["irt_global"] = irt_global

        # Per-pixel IRT raster
        irt_path = calculate_pixel_irt(
            input_path, final_path, nodata_value=nodata_value
        )
        results["irt_raster"] = irt_path

    return results


def _write_raster(path: Path, data: np.ndarray, profile: Profile) -> None:
    """Write a numpy array as a GeoTIFF raster."""
    profile.update(dtype=rasterio.float32)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(np.float32))
