"""Simplified hydraulic proxy: fill-and-spill depression flooding.

Turns a rainfall scenario into a flood-depth raster using only terrain,
no hydraulic solver:

    effective volume = rainfall_mm x runoff_coeff x zone area
    depth per cell   = water assigned by elevation priority, capped at the
                       cell's depression storage (dem_filled - dem_reprojected)

Elevation priority via a global water level L: each depression cell holds
clip(L - ground, 0, storage); total stored volume rises monotonically with L,
so L is found by bisection until stored volume matches the effective volume.
Lowest cells flood first, exactly like slowly raising a water table.

Not modeled (intentional MVP scope, see README.md in this package):
overland flow between depressions, time dynamics, drainage infrastructure.
Excess volume beyond total depression capacity is assumed to leave the zone.

Usage:
    python -m src.hydraulics.proxy     # all scenarios in scenarios.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import rasterio

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
DEM_REPROJECTED = PROCESSED / "dem_reprojected.tif"
DEM_FILLED = PROCESSED / "dem_filled.tif"
SCENARIOS_JSON = PROCESSED / "scenarios.json"

NODATA = -9999.0
DEFAULT_RUNOFF_COEFF = 0.75  # dense urban: most rain becomes surface runoff


def load_storage() -> tuple[np.ma.MaskedArray, np.ma.MaskedArray, dict, float]:
    """Depression storage depth (m) per cell, plus ground elevation and profile.

    storage = hydrologically filled DEM minus original: how deep water can
    stand in each cell before it would spill over the depression's rim.
    """
    with rasterio.open(DEM_REPROJECTED) as src:
        ground = src.read(1, masked=True)
        profile = src.profile.copy()
        cell_area = abs(src.res[0] * src.res[1])
    with rasterio.open(DEM_FILLED) as src:
        filled = src.read(1, masked=True)

    storage = np.ma.clip(filled - ground, 0, None)
    return storage, ground, profile, cell_area


def _solve_water_level(
    ground: np.ndarray, storage: np.ndarray, target_volume: float, cell_area: float
) -> float:
    """Bisect the global water level L (absolute elevation, m) so that the
    stored volume sum(clip(L - ground, 0, storage)) * cell_area hits target."""
    finite = np.isfinite(ground)  # masked cells carry ground=inf; exclude them
    lo = float(ground[finite].min())
    hi = float((ground[finite] + storage[finite]).max())

    def stored(level: float) -> float:
        return float(np.clip(level - ground, 0, storage).sum()) * cell_area

    if target_volume >= stored(hi):
        return hi  # everything full; excess assumed to drain out of zone

    for _ in range(60):  # 60 halvings: sub-micrometer precision, cheap
        mid = (lo + hi) / 2
        if stored(mid) < target_volume:
            lo = mid
        else:
            hi = mid
    return hi


def simulate(
    scenario: dict,
    runoff_coeff: float = DEFAULT_RUNOFF_COEFF,
    out_dir: Path = PROCESSED,
) -> Path:
    """Produce depth_<scenario_name>.tif for one scenario from scenarios.json.

    Output contract (see src/hydraulics/README.md): float32 GeoTIFF, meters,
    same grid/CRS as dem_reprojected.tif, nodata -9999. Track B's HEC-RAS
    adapter must emit exactly this format.
    """
    if not 0 < runoff_coeff <= 1:
        raise ValueError(f"runoff_coeff must be in (0, 1], got {runoff_coeff}")

    storage, ground, profile, cell_area = load_storage()
    valid = ~storage.mask if storage.mask is not np.ma.nomask else np.ones(storage.shape, bool)

    n_cells = int(valid.sum())
    zone_area = n_cells * cell_area
    rainfall_m = scenario["rainfall_mm"] / 1000.0
    volume = rainfall_m * runoff_coeff * zone_area  # m3 of surface water

    g = ground.filled(np.inf)  # masked cells can never be below water level
    s = storage.filled(0.0)
    level = _solve_water_level(g, s, volume, cell_area)
    depth = np.clip(level - g, 0, s).astype("float32")

    stored_volume = float(depth[valid].sum()) * cell_area
    capacity = float(s[valid].sum()) * cell_area
    logger.info(
        "%s: %d mm x %.2f runoff = %.2f Mm3; stored %.2f Mm3 (%.0f%% of %.2f Mm3 capacity), "
        "flooded cells %d (%.1f%%), max depth %.2f m",
        scenario["name"], scenario["rainfall_mm"], runoff_coeff, volume / 1e6,
        stored_volume / 1e6, 100 * stored_volume / capacity, capacity / 1e6,
        int((depth > 0.01).sum()), 100 * (depth > 0.01).sum() / n_cells, depth.max(),
    )
    if volume > capacity:
        logger.warning(
            "%s: volume exceeds total depression capacity by %.2f Mm3 — "
            "excess assumed to drain out of zone (no overland routing modeled)",
            scenario["name"], (volume - capacity) / 1e6,
        )

    out = depth.copy()
    out[~valid] = NODATA
    profile.update(dtype="float32", nodata=NODATA)

    out_path = out_dir / f"depth_{scenario['name']}.tif"
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(out, 1)
    logger.info("Depth raster written -> %s", out_path.name)
    return out_path


def simulate_all(runoff_coeff: float = DEFAULT_RUNOFF_COEFF) -> list[Path]:
    """Run every scenario in scenarios.json; one depth raster each."""
    payload = json.loads(SCENARIOS_JSON.read_text())
    return [simulate(s, runoff_coeff) for s in payload["scenarios"]]


if __name__ == "__main__":
    simulate_all()
