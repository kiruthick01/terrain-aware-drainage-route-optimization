"""Run the Phase 1 terrain pipeline end-to-end.

Usage:
    python -m src.pipeline.run

Raw input:  data/raw/chennai_velachery_dem.tif
Outputs:    data/processed/{dem_clipped,dem_reprojected,slope,aspect}.tif
Exits non-zero if any step or sanity check fails.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import rasterio

from src.pipeline import terrain

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pipeline.run")

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

DEM_RAW = RAW / "chennai_velachery_dem.tif"
BOUNDARY = RAW / "zone_boundary.geojson"  # used automatically once it exists

DEM_CLIPPED = PROCESSED / "dem_clipped.tif"
DEM_REPROJECTED = PROCESSED / "dem_reprojected.tif"
SLOPE = PROCESSED / "slope.tif"
ASPECT = PROCESSED / "aspect.tif"


def _read_valid(path: Path) -> np.ndarray:
    """Read band 1 with nodata cells masked out."""
    with rasterio.open(path) as src:
        data = src.read(1, masked=True)
    return data.compressed()


def sanity_checks() -> list[str]:
    """Return a list of failure messages; empty list means all good."""
    failures: list[str] = []

    for path in (DEM_CLIPPED, DEM_REPROJECTED, SLOPE, ASPECT):
        if not path.exists():
            failures.append(f"missing output: {path.relative_to(ROOT)}")
    if failures:
        return failures  # can't check contents of files that don't exist

    with rasterio.open(DEM_REPROJECTED) as src:
        if src.crs.to_string() != terrain.TARGET_CRS:
            failures.append(
                f"dem_reprojected CRS is {src.crs}, expected {terrain.TARGET_CRS}"
            )
        xres, yres = src.res
        # SRTM is ~30m; anything wildly off means a broken transform.
        if not (20 <= xres <= 40 and 20 <= yres <= 40):
            failures.append(f"cell size {xres:.1f}x{yres:.1f}m outside 20-40m range")

    elev = _read_valid(DEM_REPROJECTED)
    # Source DEM spans -6..44m; bilinear resampling cannot exceed input range.
    if elev.min() < -10 or elev.max() > 60:
        failures.append(f"elevation range implausible: {elev.min():.1f}..{elev.max():.1f}m")

    slope = _read_valid(SLOPE)
    if slope.min() < 0 or slope.max() > 90:
        failures.append(f"slope outside [0, 90] degrees: {slope.min():.1f}..{slope.max():.1f}")
    if slope.max() == 0:
        failures.append("slope is zero everywhere — computation likely failed")

    aspect = _read_valid(ASPECT)
    # WhiteboxTools marks flat cells (no downhill direction) with -1.
    directional = aspect[aspect != -1]
    if directional.min() < 0 or directional.max() > 360:
        failures.append(
            f"aspect outside [0, 360] degrees: {directional.min():.1f}..{directional.max():.1f}"
        )

    return failures


def main() -> int:
    PROCESSED.mkdir(parents=True, exist_ok=True)

    with terrain.load_dem(DEM_RAW):
        pass  # validation only; each step below opens the file itself

    boundary = BOUNDARY if BOUNDARY.exists() else None
    terrain.clip_dem(DEM_RAW, DEM_CLIPPED, boundary)
    terrain.reproject_dem(DEM_CLIPPED, DEM_REPROJECTED)
    terrain.compute_slope(DEM_REPROJECTED, SLOPE)
    terrain.compute_aspect(DEM_REPROJECTED, ASPECT)

    failures = sanity_checks()
    if failures:
        for f in failures:
            logger.error("SANITY FAIL: %s", f)
        return 1

    logger.info("All outputs written to %s — sanity checks passed.", PROCESSED.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
