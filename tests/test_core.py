"""Tests for phydroperiod core module."""

import numpy as np
import pytest

from phydroperiod.core import calculate_scene_weights


class TestCalculateSceneWeights:
    """Tests for calculate_scene_weights."""

    def test_single_scene(self):
        """Single scene should receive 365 days."""
        files = ["20200915_flood.tif"]
        weights = calculate_scene_weights(files)

        assert len(weights) == 1
        assert weights["20200915"] == 365

    def test_two_scenes(self):
        """Two scenes should split 365 days."""
        files = ["20200915_flood.tif", "20210215_flood.tif"]
        weights = calculate_scene_weights(files)

        assert len(weights) == 2
        # Sum should be approximately 365
        assert abs(sum(weights.values()) - 365) < 1

    def test_empty_list(self):
        """Empty list should return empty dictionary."""
        weights = calculate_scene_weights([])
        assert weights == {}

    def test_date_extraction_from_path(self):
        """Should extract dates correctly from full paths."""
        files = [
            "/path/to/data/20200915_flood.tif",
            "/another/path/20201015_mask.tif",
        ]
        weights = calculate_scene_weights(files)

        assert "20200915" in weights
        assert "20201015" in weights

    def test_weights_sum_to_365(self):
        """Weights should sum to approximately 365."""
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
