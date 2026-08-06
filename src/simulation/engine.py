"""What-if engine: flood depth for any (rainfall, runoff_coeff) in <1s.

Interpolates between the precomputed proxy depth rasters instead of running
the proxy per query. Anchors are the scenarios in scenarios.json plus a
physical zero anchor (0 mm rain -> 0 m depth everywhere).

Runoff coefficient handling — exact, not approximate: the proxy's output
depends only on effective volume (rainfall x coeff x area), so
(rainfall, coeff) is equivalent to (rainfall x coeff / 0.75, 0.75), and the
coefficient folds into an "equivalent rainfall" before interpolation.
CAVEAT: this identity is a property of the fill-and-spill proxy. Track B's
HEC-RAS output is time-dynamic and will NOT obey it — real hydraulics needs
per-coefficient precomputed runs.

Above the largest precomputed scenario the result is CLAMPED, not
extrapolated: the top scenario already uses ~96% of total depression
capacity, so linear extrapolation would exceed physical storage.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
SCENARIOS_JSON = PROCESSED / "scenarios.json"

NODATA = -9999.0
BASE_RUNOFF_COEFF = 0.75  # every precomputed raster was generated at this


@lru_cache(maxsize=1)
def _anchors() -> tuple[tuple[float, ...], np.ndarray, np.ndarray]:
    """Load all depth rasters once: (rainfall_mms, stack, valid_mask).

    stack[i] is the depth grid for rainfall_mms[i], float32, NODATA at
    invalid cells. Index 0 is the synthetic 0 mm -> all-zero anchor.
    """
    payload = json.loads(SCENARIOS_JSON.read_text())
    scenarios = sorted(payload["scenarios"], key=lambda s: s["rainfall_mm"])

    grids, rains = [], [0.0]
    for s in scenarios:
        with rasterio.open(PROCESSED / f"depth_{s['name']}.tif") as src:
            grids.append(src.read(1))
        rains.append(float(s["rainfall_mm"]))

    valid = grids[0] != NODATA
    zero = np.where(valid, np.float32(0.0), np.float32(NODATA))
    stack = np.stack([zero] + grids)
    logger.info(
        "Engine loaded %d anchors (0-%.0f mm), grid %s", len(rains), rains[-1], stack.shape[1:]
    )
    return tuple(rains), stack, valid


def get_flood_state(rainfall_mm: float, runoff_coeff: float = BASE_RUNOFF_COEFF) -> np.ndarray:
    """Depth grid (float32, meters, NODATA=-9999) for a what-if query.

    Linear per-cell interpolation between the two anchors bracketing the
    equivalent rainfall; clamped at the top anchor.
    """
    if rainfall_mm < 0:
        raise ValueError(f"rainfall_mm must be >= 0, got {rainfall_mm}")
    if not 0 < runoff_coeff <= 1:
        raise ValueError(f"runoff_coeff must be in (0, 1], got {runoff_coeff}")

    rains, stack, valid = _anchors()
    eq_rain = rainfall_mm * runoff_coeff / BASE_RUNOFF_COEFF

    if eq_rain >= rains[-1]:
        if eq_rain > rains[-1]:
            logger.warning(
                "equivalent rainfall %.0f mm beyond top anchor %.0f mm — clamping "
                "(no extrapolation past depression capacity)", eq_rain, rains[-1],
            )
        return stack[-1].copy()

    hi = int(np.searchsorted(rains, eq_rain, side="right"))
    lo = hi - 1
    t = (eq_rain - rains[lo]) / (rains[hi] - rains[lo])
    depth = (1 - t) * stack[lo] + t * stack[hi]
    # Lerp of two NODATA values is NODATA already; enforce exactly anyway.
    depth = np.where(valid, depth, np.float32(NODATA)).astype("float32")
    return depth


if __name__ == "__main__":
    import time

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    get_flood_state(100)  # warm the cache before timing queries
    for mm in (0, 30, 75, 125, 200, 300, 350, 500):
        t0 = time.perf_counter()
        d = get_flood_state(mm)
        dt = (time.perf_counter() - t0) * 1000
        wet = d[d != NODATA]
        print(
            f"{mm:>4} mm: {dt:6.2f} ms, flooded {(wet > 0.01).sum():>6} cells, "
            f"mean wet depth {wet[wet > 0.01].mean() if (wet > 0.01).any() else 0:.2f} m, "
            f"max {wet.max():.2f} m"
        )
