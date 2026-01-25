"""
Basic usage example for phydroperiod library.

This script shows how to calculate hydroperiod from
a directory containing water masks.
"""

from pathlib import Path

from phydroperiod import compute_hydroperiod


def main():
    # Path to directory with water masks
    # Masks must be GeoTIFF (0=dry, 1=water, 2=nodata)
    # with filenames starting with YYYYMMDD
    masks_dir = Path("/path/to/water_masks")

    # Calculate hydroperiod (complete pipeline)
    print(f"Processing masks in: {masks_dir}")

    results = compute_hydroperiod(
        input_path=masks_dir,
        normalize=True,  # Normalize to 365 days (as integer)
        compute_first_last=True,  # Calculate first/last flood day
        compute_irt=True,  # Calculate Temporal Representativity Index
    )

    # Show results
    print("\nGenerated products:")
    print(f"  - Intermediate: {results['intermediate_dir']}")
    print(f"  - Hydroperiod: {results['hydroperiod']}")
    print(f"  - Valid days: {results['valid_days']}")
    print(f"  - Normalized (int): {results['normalized']}")
    print(f"  - First flood DOY: {results['first_flood_doy']}")
    print(f"  - Last flood DOY: {results['last_flood_doy']}")
    print(f"  - First flood date: {results['first_flood_date']}")
    print(f"  - Last flood date: {results['last_flood_date']}")
    print(f"  - IRT raster: {results['irt_raster']}")

    print(f"\nGlobal Temporal Representativity Index (IRT): {results['irt_global']}")

    if results['irt_global'] < 0.5:
        print("  Warning: Low IRT - observations are poorly distributed throughout the year")


if __name__ == "__main__":
    main()
