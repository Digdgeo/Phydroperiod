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
        normalize=True,  # Normalize to 365 days
    )

    # Show results
    print("\nGenerated products:")
    print(f"  - Intermediate: {results['intermediate_dir']}")
    print(f"  - Hydroperiod: {results['hydroperiod']}")
    print(f"  - Valid days: {results['valid_days']}")
    print(f"  - Normalized: {results['normalized']}")


if __name__ == "__main__":
    main()
