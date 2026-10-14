# Changelog

## 0.1.4 — 2026-10-14

### Fixed

- **The hydrological cycle was taken from the smallest calendar year in the
  filenames, which is wrong for any cycle whose first usable scene falls after
  New Year.** A 2020/21 cycle first seen on 2021-01-12 — an autumn clouded out,
  which in a Landsat archive is ordinary — was read as cycle 2021, putting `d0`
  a year ahead of every scene. The first scene then came out with a weight of
  **−215 days** and the last with **399.5**, and because a negative weight is
  handed to `np.where(mask == water, weight, 0)`, pixels that held water in that
  scene had flood days *subtracted*. The weights still summed to exactly 365, so
  nothing downstream could notice.

  Dates are now mapped to the cycle they belong to before the earliest is taken
  (`_cycle_year`, `_base_year`), and the cycle is resolved **once** in
  `compute_hydroperiod` and handed to every step. Each step used to work it out
  from the filenames on its own, in five separate places, so they could disagree.

- **`_doy_to_date_int` assumed 1 September regardless of
  `hydrological_year_start`.** Any other cycle start converted days to dates
  against the wrong origin, so `first_flood_date` and `last_flood_date` were
  shifted while `first_flood_doy` and `last_flood_doy` were right. The cycle
  start is now a parameter, and the end of the cycle is derived from it rather
  than hardcoded to 31 August.

- **`__version__` still read `0.1.0`** three releases after the fact.

### Added

- `hyd_year` on `calculate_scene_weights`, `accumulate_hydroperiod`,
  `calculate_first_last_flood`, `calculate_temporal_representativity`,
  `calculate_pixel_irt` and `compute_hydroperiod`: the cycle's base year, i.e.
  2020 for 2020/21. Inferred from the scene dates when omitted, as before, but
  passing it removes the inference — which is what `ndvi2gif` does, where the
  cycle is an argument and never guessed.

- `hydrological_year_start` on `accumulate_hydroperiod`,
  `calculate_first_last_flood` and `compute_hydroperiod`, which took the default
  from whichever function happened to compute it.

- A warning when the scenes handed in span more than one hydrological cycle.
  Midpoint weights only mean anything within one cycle, so a mixed collection is
  a mistake worth naming rather than averaging over.

### Notes

- The midpoint weighting itself is unchanged, and was checked term by term
  against the implementation in `ndvi2gif` (`hydroperiod.py::_add_scene_weights`)
  over five scene layouts — a full cycle of 12 scenes, a poor cycle of 6, two
  sensors with near-coincident dates, two scenes and one. The two agree
  **exactly**, to 0.0, and both sum to 365.

- The test suite had been written against an earlier API, when
  `calculate_scene_weights` returned `{date: weight}` rather than
  `{date: {'weight', 'start', 'end'}}`; three of its five tests could not pass.
  Rewritten, with the midpoint formula pinned by hand and the cycle bug covered
  by regression tests.

### Still open

- `calculate_first_last_flood` has neither of the two guards that `ndvi2gif`
  applies before reporting an onset or a recession date: a minimum number of
  flood days (`min_flood_days=3`, which drops pixels whose single wet scene is
  cloud noise) and a permanence threshold (`permanent_threshold=0.95`, which
  gives sea and permanent lagoons fixed 0/365 boundaries, since onset and
  recession mean nothing there).

- `normalize_hydroperiod` divides the **rounded** `int16` rasters that
  `accumulate_hydroperiod` wrote, whereas `ndvi2gif` divides the unrounded sums.
  The reported value is an integer either way; what differs is where the
  rounding happens, and the error is amplified by `365 / valid_days`. Negligible
  on a well-covered cycle (0.2 days), up to 8 days on a cloudy one and 18 on a
  pixel whose autumn was lost — which are the cycles that matter most.

## 0.1.3 and earlier

Initial releases: midpoint weighting after Javier Bustamante's scheme, per-pixel
valid-observation tracking, first and last flood day, temporal representativity
index (global and per pixel), and normalisation to a 365-day cycle.
