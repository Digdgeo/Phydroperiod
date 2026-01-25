"""
Phydroperiod - Hydroperiod calculation from water masks.

This library calculates hydroperiod (flood days) from
a time series of water masks.
"""

from .core import (
    calculate_scene_weights,
    process_masks,
    accumulate_hydroperiod,
    normalize_hydroperiod,
    compute_hydroperiod,
    calculate_first_last_flood,
    calculate_temporal_representativity,
    calculate_pixel_irt,
)

__version__ = "0.1.0"
__author__ = "Diego García Díaz"

__all__ = [
    "calculate_scene_weights",
    "process_masks",
    "accumulate_hydroperiod",
    "normalize_hydroperiod",
    "compute_hydroperiod",
    "calculate_first_last_flood",
    "calculate_temporal_representativity",
    "calculate_pixel_irt",
]
