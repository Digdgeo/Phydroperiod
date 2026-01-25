"""
Phydroperiod - Cálculo de hidroperiodo a partir de máscaras de agua.

Esta librería permite calcular el hidroperiodo (días de inundación)
a partir de una serie temporal de máscaras de agua binarias.
"""

from .core import (
    calculate_scene_weights,
    process_masks,
    accumulate_hydroperiod,
    normalize_hydroperiod,
    compute_hydroperiod,
)

__version__ = "0.1.0"
__author__ = "Diego García Díaz"

__all__ = [
    "calculate_scene_weights",
    "process_masks",
    "accumulate_hydroperiod",
    "normalize_hydroperiod",
    "compute_hydroperiod",
]
