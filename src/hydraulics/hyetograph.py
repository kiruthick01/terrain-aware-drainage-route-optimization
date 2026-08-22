"""Rainfall hyetographs: time-distribute each scenario's daily rainfall
total into a synthetic 24-hour design-storm shape for HEC-RAS rain-on-grid.

Why not the literal NRCS Type II table: the standard SCS/NRCS Type II
24-hour distribution is normally read from a tabulated ordinate list (NEH
Part 630 Chapter 4 / TR-55 Appendix B, 6-minute increments). Every source
found for that table while scoping this module -- NRCS/USDA PDFs, state DOT
manuals, vendor docs -- turned out to be a scanned image or embedded figure,
not machine-readable text, and this project has no OCR available to verify
digit-level values against them. Hand-transcribing an unverifiable table
into a hydraulic model input was judged worse than an honestly-labeled
approximation. See devlog/22-08-26.md for the research trail.

What's used instead: a logistic (sigmoid) cumulative curve, centered on the
storm's midpoint (PEAK_HOUR = 12h) and calibrated so PEAK_HOUR_FRACTION of
the 24-hour total falls within the single hour surrounding the peak -- the
one summary statistic about Type II that was consistently corroborated
across every source consulted (commonly cited as roughly 40-43%). This
reproduces Type II's defining character -- long quiet build-up, one sharp
burst near mid-storm, quick taper -- without claiming NRCS-table precision
that couldn't be verified. Resolution is 30-minute steps: coarser than the
real table's 6-minute ordinates (a deliberate simplification, not an
attempt at table fidelity -- a smooth curve can't reproduce a sharper
sub-peak without also fabricating structure this project has no basis for).

If exact NRCS compliance is later required (e.g. validating against the
real Dec 2015 event in Phase 3), source NEH630 Ch.4's table from an OCR'd
copy and replace build_hyetograph's body -- everything downstream only
depends on the output contract below, not on how the shape was generated.

Output contract: build_hyetograph() returns a DataFrame with columns `hour`
(> 0, step DT_HR, up to duration_hr) and `incremental_mm` (rain falling in
that step); `incremental_mm.sum()` equals the scenario's daily rainfall_mm
exactly. generate_all() writes one CSV per scenario in scenarios.json to
data/processed/hyetographs/<scenario>.csv -- one file per rainfall
scenario. The 3 antecedent-moisture (AMC) variants from
src/pipeline/landuse.py reuse the same hyetograph per scenario; AMC only
changes the loss layer (curve_number_{dry,wet}.tif), not the rainfall input.

Open item (not yet resolved): how HEC-RAS actually ingests this as a
boundary condition. The native path for a 2D rain-on-grid precip BC is a
DSS time series. `pydsstools` installs on Windows but force-downgrades
numpy to <2, breaking rasterio/scipy in this project's shared venv -- not
usable without an isolated environment just for DSS writing. Given there
are only 5 files (not 15 -- AMC doesn't add hyetographs), the practical
path is a one-time manual import per scenario via HEC-DSSVue (bundled with
the HEC-RAS install), pasting/importing these CSVs. An isolated
pydsstools venv remains a fallback if that proves too tedious once 2b.5
needs to run this unattended.

Usage:
    python -m src.hydraulics.hyetograph
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
SCENARIOS_JSON = PROCESSED / "scenarios.json"
HYETOGRAPH_DIR = PROCESSED / "hyetographs"

DURATION_HR = 24.0
DT_HR = 0.5  # 30-min steps -- see module docstring for why not finer
PEAK_HOUR = 12.0  # storm midpoint, matching Type II's centered peak
PEAK_HOUR_FRACTION = 0.40  # fraction of the 24h total within the peak hour


def _sigmoid_cdf(t: np.ndarray, k: float, t0: float) -> np.ndarray:
    """Logistic CDF centered at t0, not yet rescaled to [0, 1] over [0, duration]."""
    return 1.0 / (1.0 + np.exp(-k * (t - t0)))


def _normalized_cdf(t: np.ndarray, k: float, duration_hr: float, t0: float) -> np.ndarray:
    """Rescale the logistic so F(0) = 0 and F(duration_hr) = 1 exactly."""
    lo, hi = _sigmoid_cdf(np.array([0.0, duration_hr]), k, t0)
    return (_sigmoid_cdf(t, k, t0) - lo) / (hi - lo)


def _solve_steepness(duration_hr: float, t0: float, peak_fraction: float) -> float:
    """Find the logistic steepness k so the hour centered on t0 holds
    exactly peak_fraction of the total depth."""

    def residual(k: float) -> float:
        f = _normalized_cdf(np.array([t0 - 0.5, t0 + 0.5]), k, duration_hr, t0)
        return (f[1] - f[0]) - peak_fraction

    return brentq(residual, 1e-6, 10.0)


def build_hyetograph(
    daily_total_mm: float,
    duration_hr: float = DURATION_HR,
    dt_hr: float = DT_HR,
    peak_hour: float = PEAK_HOUR,
    peak_fraction: float = PEAK_HOUR_FRACTION,
) -> pd.DataFrame:
    """Time-distribute daily_total_mm into a Type-II-like synthetic storm.

    See module docstring for why this is a calibrated logistic
    approximation rather than the literal NRCS tabulated curve.
    """
    if daily_total_mm <= 0:
        raise ValueError(f"daily_total_mm must be > 0, got {daily_total_mm}")
    if not 0 <= peak_hour - 0.5 or not peak_hour + 0.5 <= duration_hr:
        raise ValueError(f"peak_hour {peak_hour} too close to the storm edge for a 1h peak window")

    k = _solve_steepness(duration_hr, peak_hour, peak_fraction)
    edges = np.arange(0.0, duration_hr + dt_hr / 2, dt_hr)
    cdf = _normalized_cdf(edges, k, duration_hr, peak_hour)
    cdf[0], cdf[-1] = 0.0, 1.0  # pin exactly; float error would otherwise leak mm

    incremental = np.diff(cdf) * daily_total_mm
    df = pd.DataFrame({"hour": edges[1:], "incremental_mm": incremental})

    total = incremental.sum()
    if not np.isclose(total, daily_total_mm, rtol=1e-6):
        raise RuntimeError(f"hyetograph mass balance failed: {total:.4f} != {daily_total_mm}")

    peak_actual = incremental[(df["hour"] > peak_hour - 0.5) & (df["hour"] <= peak_hour + 0.5)].sum()
    logger.info(
        "Hyetograph built: %.0f mm over %.0fh, peak hour %.1f-%.1f holds %.1f%% (target %.0f%%)",
        daily_total_mm, duration_hr, peak_hour - 0.5, peak_hour + 0.5,
        100 * peak_actual / daily_total_mm, 100 * peak_fraction,
    )
    return df


def generate_all(out_dir: Path = HYETOGRAPH_DIR) -> list[Path]:
    """Build and write one hyetograph CSV per scenario in scenarios.json."""
    payload = json.loads(SCENARIOS_JSON.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for s in payload["scenarios"]:
        df = build_hyetograph(s["rainfall_mm"])
        path = out_dir / f"{s['name']}.csv"
        df.to_csv(path, index=False)
        logger.info("Hyetograph written -> %s", path.name)
        paths.append(path)
    return paths


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    generate_all()
