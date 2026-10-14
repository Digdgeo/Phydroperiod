"""Tests for phydroperiod core module."""

import warnings
from datetime import date

import pytest

from phydroperiod.core import _base_year, _cycle_year, calculate_scene_weights


class TestCalculateSceneWeights:
    """Tests for calculate_scene_weights."""

    def test_single_scene(self):
        """Single scene should receive 365 days."""
        files = ["20200915_flood.tif"]
        weights = calculate_scene_weights(files)

        assert len(weights) == 1
        assert weights["20200915"]["weight"] == 365
        assert weights["20200915"]["start"] == 0
        assert weights["20200915"]["end"] == 365

    def test_two_scenes(self):
        """Two scenes should split 365 days."""
        files = ["20200915_flood.tif", "20210215_flood.tif"]
        weights = calculate_scene_weights(files)

        assert len(weights) == 2
        assert abs(sum(w["weight"] for w in weights.values()) - 365) < 1e-9

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
        """Weights should sum to 365."""
        files = [
            "20200915_flood.tif",
            "20201015_flood.tif",
            "20201115_flood.tif",
            "20201215_flood.tif",
            "20210115_flood.tif",
        ]
        weights = calculate_scene_weights(files)

        total = sum(w["weight"] for w in weights.values())
        assert abs(total - 365) < 1e-9

    def test_ranges_are_contiguous(self):
        """Each scene's range starts where the previous one ended."""
        files = [
            "20200915_flood.tif",
            "20201115_flood.tif",
            "20210115_flood.tif",
            "20210715_flood.tif",
        ]
        weights = calculate_scene_weights(files)
        ordered = [weights[k] for k in sorted(weights)]

        assert ordered[0]["start"] == 0
        assert ordered[-1]["end"] == 365
        for before, after in zip(ordered, ordered[1:]):
            assert before["end"] == after["start"]

    def test_midpoint_formula(self):
        """A boundary is the midpoint between two consecutive scenes.

        Worked out by hand so the formula itself is pinned and not only its
        invariants: 2020-09-15 is day 14 from 1 September and 2020-10-15 is
        day 44, so the boundary between them falls on day 29.
        """
        weights = calculate_scene_weights(
            ["20200915_flood.tif", "20201015_flood.tif"]
        )

        assert weights["20200915"]["end"] == 29
        assert weights["20201015"]["start"] == 29
        assert weights["20200915"]["weight"] == 29
        assert weights["20201015"]["weight"] == 365 - 29


class TestCycleYear:
    """Which hydrological cycle a date belongs to."""

    def test_on_and_after_the_start_day(self):
        """From the start day onwards, the cycle is that calendar year."""
        assert _cycle_year(date(2020, 9, 1), (9, 1)) == 2020
        assert _cycle_year(date(2020, 12, 31), (9, 1)) == 2020

    def test_before_the_start_day(self):
        """Before the start day, a date belongs to the previous cycle."""
        assert _cycle_year(date(2021, 1, 12), (9, 1)) == 2020
        assert _cycle_year(date(2021, 8, 31), (9, 1)) == 2020

    def test_honours_a_different_start(self):
        """The start day is a parameter, not an assumption."""
        assert _cycle_year(date(2020, 9, 15), (10, 1)) == 2019
        assert _cycle_year(date(2020, 10, 1), (10, 1)) == 2020


class TestBaseYearRegression:
    """A cycle first seen after New Year used to be read a year late.

    Taking the smallest calendar year in the filenames put ``d0`` a year ahead
    of every scene, which gave the first scene a large negative weight and the
    last one more than a year — **while the weights still summed to exactly
    365**, so no aggregate check could catch it.
    """

    # A 2020/21 cycle with its autumn clouded out: nothing usable until January.
    AUTUMN_CLOUDED_OUT = [
        "20210112_flood.tif",
        "20210215_flood.tif",
        "20210403_flood.tif",
        "20210520_flood.tif",
        "20210712_flood.tif",
        "20210814_flood.tif",
    ]

    def test_no_negative_weights(self):
        """The bug's signature was a negative weight on the first scene."""
        weights = calculate_scene_weights(self.AUTUMN_CLOUDED_OUT)

        for date_str, scene in weights.items():
            assert scene["weight"] > 0, f"{date_str} weighs {scene['weight']}"
            assert scene["start"] >= 0
            assert scene["end"] > 0

    def test_weights_stay_within_the_cycle(self):
        """No scene may be handed more days than the cycle has."""
        weights = calculate_scene_weights(self.AUTUMN_CLOUDED_OUT)

        for scene in weights.values():
            assert scene["weight"] <= 365
            assert scene["end"] <= 365

    def test_the_sum_was_never_the_symptom(self):
        """It summed to 365 before the fix too, which is why it went unseen."""
        weights = calculate_scene_weights(self.AUTUMN_CLOUDED_OUT)

        total = sum(w["weight"] for w in weights.values())
        assert abs(total - 365) < 1e-9

    def test_first_boundary_counts_from_the_cycle_start(self):
        """2021-01-12 is day 133 of cycle 2020/21 and 2021-02-15 is day 167."""
        weights = calculate_scene_weights(self.AUTUMN_CLOUDED_OUT)

        assert weights["20210112"]["weight"] == pytest.approx(150.0)

    def test_base_year_is_the_cycle_not_the_calendar_year(self):
        """The cycle is 2020/21 even though every filename reads 2021."""
        dates = [f[:8] for f in self.AUTUMN_CLOUDED_OUT]

        assert _base_year(dates, (9, 1)) == 2020

    def test_explicit_hyd_year_wins(self):
        """Passing the cycle removes the guess entirely."""
        dates = [f[:8] for f in self.AUTUMN_CLOUDED_OUT]
        assert _base_year(dates, (9, 1), hyd_year=2019) == 2019

        weights = calculate_scene_weights(self.AUTUMN_CLOUDED_OUT, hyd_year=2020)
        assert all(w["weight"] > 0 for w in weights.values())

    def test_a_normal_cycle_is_unaffected(self):
        """A cycle that starts in autumn answers exactly as it did before."""
        files = [
            "20200915_flood.tif",
            "20201118_flood.tif",
            "20210121_flood.tif",
            "20210630_flood.tif",
        ]
        dates = [f[:8] for f in files]

        assert _base_year(dates, (9, 1)) == 2020
        weights = calculate_scene_weights(files)
        assert weights["20200915"]["start"] == 0
        assert all(w["weight"] > 0 for w in weights.values())

    def test_scenes_spanning_two_cycles_warn(self):
        """Weights only mean something within one cycle, so say so."""
        dates = ["20200915", "20210915"]

        with pytest.warns(UserWarning, match="span 2 hydrological cycles"):
            assert _base_year(dates, (9, 1)) == 2020

    def test_one_cycle_does_not_warn(self):
        """The warning must not fire on ordinary input."""
        dates = ["20200915", "20210115", "20210814"]

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert _base_year(dates, (9, 1)) == 2020
