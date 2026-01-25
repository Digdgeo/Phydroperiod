"""Tests para el módulo core de phydroperiod."""

import numpy as np
import pytest

from phydroperiod.core import calculate_scene_weights


class TestCalculateSceneWeights:
    """Tests para calculate_scene_weights."""

    def test_single_scene(self):
        """Una sola escena debe recibir 365 días."""
        files = ["20200915_flood.tif"]
        weights = calculate_scene_weights(files)

        assert len(weights) == 1
        assert weights["20200915"] == 365

    def test_two_scenes(self):
        """Dos escenas deben dividir 365 días."""
        files = ["20200915_flood.tif", "20210215_flood.tif"]
        weights = calculate_scene_weights(files)

        assert len(weights) == 2
        # La suma debe ser aproximadamente 365
        assert abs(sum(weights.values()) - 365) < 1

    def test_empty_list(self):
        """Lista vacía debe retornar diccionario vacío."""
        weights = calculate_scene_weights([])
        assert weights == {}

    def test_date_extraction_from_path(self):
        """Debe extraer fechas correctamente de rutas completas."""
        files = [
            "/path/to/data/20200915_flood.tif",
            "/another/path/20201015_mask.tif",
        ]
        weights = calculate_scene_weights(files)

        assert "20200915" in weights
        assert "20201015" in weights

    def test_weights_sum_to_365(self):
        """Los pesos deben sumar aproximadamente 365."""
        files = [
            "20200915_flood.tif",
            "20201015_flood.tif",
            "20201115_flood.tif",
            "20201215_flood.tif",
            "20210115_flood.tif",
        ]
        weights = calculate_scene_weights(files)

        total = sum(weights.values())
        assert abs(total - 365) < 1
