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
) -> Dict[str, float]:
    """Calculate the weight in days for each scene within a hydrological cycle.

    Distributes 365 days among available scenes, assigning each one
    a day range proportional to its temporal position.

    Args:
        mask_files: List of paths to mask files. Filenames must
            start with YYYYMMDD format (e.g., 20200315_flood.tif).
        hydrological_year_start: Tuple (month, day) of the hydrological
            cycle start. Default (9, 1) = September 1st.

    Returns:
        Dictionary {scene_date: assigned_days}.

    Example:
        >>> files = ["20200915_flood.tif", "20201015_flood.tif", "20201115_flood.tif"]
        >>> weights = calculate_scene_weights(files)
        >>> print(weights)
        {'20200915': 30.0, '20201015': 30.5, '20201115': 304.5}
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

    # Calculate value (days) for each scene
    values = []
    if cutpoints:
        values.append(cutpoints[0])
        for i in range(len(cutpoints) - 1):
            values.append(cutpoints[i + 1] - cutpoints[i])
        values.append(365 - cutpoints[-1])
    else:
        # Single scene, assign 365 days
        values.append(365)

    return dict(zip(scene_dates, values))


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

    # Get list of masks
    mask_files = sorted([f for f in input_path.glob("*.tif")])

    if not mask_files:
        raise ValueError(f"No .tif files found in {input_path}")

    # Calculate weights if not provided
    if weights is None:
        weights = calculate_scene_weights([str(f) for f in mask_files])

    # Process each mask
    for mask_file in mask_files:
        date_str = mask_file.name[:8]
        weight = weights.get(date_str, 0)

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

    # Save results
    hydroperiod_path = output_path / f"hydroperiod{cycle_suffix}.tif"
    valid_days_path = output_path / f"valid_days{cycle_suffix}.tif"

    _write_raster(hydroperiod_path, flood_sum, profile)
    _write_raster(valid_days_path, valid_sum, profile)

    return hydroperiod_path, valid_days_path


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
                normalized = np.clip(normalized, 0, target_days).astype(np.float32)

    output_file = output_path / f"hydroperiod_nor_{cycle}.tif"
    _write_raster(output_file, normalized, profile)

    return output_file


def compute_hydroperiod(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    normalize: bool = True,
    target_days: int = 365,
    water_value: int = 1,
    dry_value: int = 0,
    nodata_value: int = 2,
) -> Dict[str, Path]:
    """Complete pipeline to calculate hydroperiod.

    Executes all calculation steps:
    1. Calculate weights per scene
    2. Process masks generating intermediate products
    3. Accumulate total hydroperiod
    4. (Optional) Normalize to target days

    Args:
        input_path: Directory with water masks (.tif).
            Filenames with YYYYMMDD*.tif format.
        output_path: Base output directory. If not specified,
            subdirectories are created in input_path.
        normalize: If True, also generates normalized hydroperiod.
        target_days: Target days for normalization.
        water_value: Value representing water/flood in masks.
            Default 1.
        dry_value: Value representing dry land in masks.
            Default 0.
        nodata_value: Value representing nodata (clouds, shadows, etc.).
            Default 2. These pixels are excluded from calculation.

    Returns:
        Dictionary with paths to generated products:
        - 'intermediate_dir': directory with intermediate products
        - 'hydroperiod': path to accumulated hydroperiod
        - 'valid_days': path to accumulated valid days
        - 'normalized': path to normalized hydroperiod (if normalize=True)

    Example:
        >>> results = compute_hydroperiod("/path/to/masks")
        >>> print(f"Hydroperiod: {results['hydroperiod']}")
        Hydroperiod: /path/to/masks/hydroperiod_2020_2021.tif
    """
    input_path = Path(input_path)

    if output_path is None:
        intermediate_path = input_path / "output"
        final_path = input_path
    else:
        output_path = Path(output_path)
        intermediate_path = output_path / "intermediate"
        final_path = output_path

    # Step 1 and 2: Calculate weights and process masks
    intermediate_dir = process_masks(
        input_path,
        intermediate_path,
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

    return results


def _write_raster(path: Path, data: np.ndarray, profile: Profile) -> None:
    """Write a numpy array as a GeoTIFF raster."""
    profile.update(dtype=rasterio.float32)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(np.float32))
