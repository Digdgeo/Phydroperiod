# Phydroperiod

Python library for calculating hydroperiod (flood days) from water mask time series.

## How it works

The hydroperiod calculation distributes 365 days among available scenes based on their temporal position within the hydrological cycle (September 1st - August 31st):

![Hydroperiod calculation scheme](https://raw.githubusercontent.com/Digdgeo/Phydroperiod/master/imgs/hydroperiod_scheme.png)

Scenes are irregularly spaced in time, so each one is weighted by the stretch of the
cycle it represents rather than counted as a single observation: the boundaries between
consecutive scenes are placed at the midpoints of their acquisition dates, and the first
and last scenes extend to the start and the end of the cycle, so the weights add up to
365. A pixel observed as water in a single scene therefore contributes the days that
scene stands for, not one day.

**This midpoint weighting scheme is the method of Javier Bustamante** (Estación Biológica
de Doñana, CSIC), developed for the long-term monitoring of the Doñana marshes. It has
not been described formally in the literature; a full account is in preparation. Please
credit it as his when you use this library.

On top of that scheme, this library tracks valid observations **per pixel**, so that a
partially cloudy scene contributes wherever it is clear, and derives from that the
per-pixel first and last flood day and the per-pixel temporal representativity index.

## Installation

```bash
pip install phydroperiod
```

For development:

```bash
git clone https://github.com/Digdgeo/Phydroperiod.git
cd Phydroperiod
pip install -e ".[dev]"
```

## Basic Usage

```python
from phydroperiod import compute_hydroperiod

# Calculate hydroperiod from a directory with water masks
results = compute_hydroperiod("/path/to/water_masks")

print(f"Hydroperiod: {results['hydroperiod']}")
print(f"Valid days: {results['valid_days']}")
print(f"Normalized (0-365): {results['normalized']}")
print(f"First flood (DOY): {results['first_flood_doy']}")
print(f"First flood (date): {results['first_flood_date']}")
print(f"Last flood (DOY): {results['last_flood_doy']}")
print(f"Last flood (date): {results['last_flood_date']}")
print(f"IRT raster: {results['irt_raster']}")
print(f"IRT global: {results['irt_global']}")
```

## Mask Requirements

- Format: GeoTIFF (.tif)
- Default values: 0 = dry, 1 = water, 2 = nodata (clouds, shadows, etc.)
- Filenames: must start with date in YYYYMMDD format (e.g., `20200915_flood.tif`)

Values are configurable:

## Available Functions

### `compute_hydroperiod(input_path, output_path=None, normalize=True, ...)`

Complete pipeline that executes all processing steps:

```python
from phydroperiod import compute_hydroperiod

# Basic usage (default values: 0=dry, 1=water, 2=nodata)
results = compute_hydroperiod(
    input_path="/path/to/masks",
    output_path="/path/to/output",  # optional
    normalize=True,  # generates hydroperiod normalized to 365 days
)

# With custom values
results = compute_hydroperiod(
    input_path="/path/to/masks",
    water_value=1,      # value representing water
    dry_value=0,        # value representing dry land
    nodata_value=255,   # value representing nodata
)
```

### Individual Functions

```python
from phydroperiod import (
    calculate_scene_weights,
    process_masks,
    accumulate_hydroperiod,
    normalize_hydroperiod,
    calculate_first_last_flood,
    calculate_temporal_representativity,
    calculate_pixel_irt,
)

# 1. Calculate weights per scene (includes day ranges)
weights = calculate_scene_weights(mask_files)

# 2. Process masks (generates intermediate products)
intermediate_dir = process_masks(input_path, weights=weights)

# 3. Accumulate total hydroperiod
hydroperiod_path, valid_days_path = accumulate_hydroperiod(intermediate_dir)

# 4. Normalize to 365 days (saved as integer)
normalized_path = normalize_hydroperiod(output_path)

# 5. Calculate first/last flood day per pixel (DOY and YYYYMMDD formats)
flood_dates = calculate_first_last_flood(input_path, weights=weights)

# 6. Calculate Temporal Representativity Index (global and per-pixel)
irt_global = calculate_temporal_representativity(mask_files)
irt_raster = calculate_pixel_irt(input_path)
```

## Hydrological Cycle

The calculation is based on the hydrological cycle running from September 1st to August 31st of the following year. Each scene receives a proportional weight based on its temporal position within the cycle.

## Generated Products

| File | Description |
|------|-------------|
| `*_flood_rec.tif` | Flood days per scene (intermediate) |
| `*_dry_rec.tif` | Dry days per scene (intermediate) |
| `*_valid_rec.tif` | Valid days per scene (intermediate) |
| `hydroperiod_YYYY_YYYY+1.tif` | Accumulated hydroperiod (integer) |
| `valid_days_YYYY_YYYY+1.tif` | Accumulated valid days (integer) |
| `hydroperiod_nor_YYYY_YYYY+1.tif` | Normalized hydroperiod (0-365, integer) |
| `first_flood_doy_YYYY_YYYY+1.tif` | First flood day (0-365, day of hydrological year) |
| `last_flood_doy_YYYY_YYYY+1.tif` | Last flood day (0-365, day of hydrological year) |
| `first_flood_date_YYYY_YYYY+1.tif` | First flood day (YYYYMMDD format, e.g., 20240915) |
| `last_flood_date_YYYY_YYYY+1.tif` | Last flood day (YYYYMMDD format, e.g., 20250213) |
| `irt_YYYY_YYYY+1.tif` | Temporal Representativity Index per pixel (0-1) |

## Temporal Representativity Index (IRT)

The library calculates an index (0-1) that measures how well distributed the observations are throughout the hydrological year:

- **IRT = 1**: Observations perfectly distributed across the year
- **IRT = 0**: All observations concentrated in a single period

Two IRT values are provided:

- **Global IRT** (`irt_global`): Based on the available scenes, same for all pixels
- **Per-pixel IRT** (`irt_raster`): Accounts for nodata (clouds, shadows) affecting each pixel differently. A pixel covered by clouds in summer will have lower IRT than one with observations throughout the year.

This helps assess the reliability of the hydroperiod calculation at both collection and pixel level.

## Example Output

![Valid days and hydroperiod](https://raw.githubusercontent.com/Digdgeo/Phydroperiod/master/imgs/valid_days_and_hyd_non_normalized.png)
*Accumulated valid days (left) and non-normalized hydroperiod (right) for the 2023-2024 hydrological cycle in Doñana, Spain.*

![Normalized hydroperiod](https://raw.githubusercontent.com/Digdgeo/Phydroperiod/master/imgs/normalized_hydroperiod.png)
*Normalized hydroperiod (0-365 days) for the same cycle.*

## Roadmap

- [ ] Google Earth Engine integration for water mask retrieval
- [ ] Ndvi2Gif integration for automatic mask generation
- [ ] CLI for terminal usage
- [ ] Support for multiple hydrological cycles
- [ ] Leafmap integration for interactive visualization

## Authors

- **Javier Bustamante Díaz** - Midpoint weighting scheme (core method)
- **Diego García Díaz** - Per-pixel treatment of missing data, per-pixel IRT and
  first/last flood day, development and implementation

## Citation

If you use this library, please cite the software and credit the method:

> García Díaz, D., & Bustamante Díaz, J. *Phydroperiod: hydroperiod from water mask time
> series*. https://github.com/Digdgeo/Phydroperiod

The midpoint weighting scheme is due to J. Bustamante (EBD-CSIC). A formal description is
in preparation; until it is published, please cite this repository and name the method's
author.

The Doñana monitoring programme in which the method was developed is described in:

> Díaz-Delgado, R., Aragonés, D., Afán, I., & Bustamante, J. (2016). Long-Term Monitoring
> of the Flooding Regime and Hydroperiod of Doñana Marshes with Landsat Time Series
> (1974-2014). *Remote Sensing*, 8, 775. https://doi.org/10.3390/rs8090775

Note that the hydroperiod algorithm published in that paper is the earlier, scene-level
version of the protocol: it sums the intervals between consecutive scenes in which a
pixel is flooded and does **not** use midpoint weighting. Please do not cite it as the
source of this method.

## License

MIT
