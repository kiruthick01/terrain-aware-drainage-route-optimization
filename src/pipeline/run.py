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

from src.hydraulics import proxy
from src.pipeline import rainfall, terrain
from src.simulation import engine, export

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
DEM_FILLED = PROCESSED / "dem_filled.tif"
FLOW_DIR = PROCESSED / "flow_dir.tif"
FLOW_ACC = PROCESSED / "flow_acc.tif"
RAINFALL_SAMPLE = rainfall.SAMPLE_CSV
SCENARIOS = rainfall.SCENARIOS_JSON
RAINFALL_YEAR = 2015


def _read_valid(path: Path) -> np.ndarray:
    """Read band 1 with nodata cells masked out."""
    with rasterio.open(path) as src:
        data = src.read(1, masked=True)
    return data.compressed()


def sanity_checks() -> list[str]:
    """Return a list of failure messages; empty list means all good."""
    failures: list[str] = []

    for path in (DEM_CLIPPED, DEM_REPROJECTED, SLOPE, ASPECT, DEM_FILLED, FLOW_DIR, FLOW_ACC):
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

    # Filling only raises cells, never lowers them (epsilon for float32 noise).
    with rasterio.open(DEM_REPROJECTED) as a, rasterio.open(DEM_FILLED) as b:
        orig = a.read(1, masked=True)
        filled = b.read(1, masked=True)
    diff = (filled - orig).compressed()
    if diff.min() < -0.001:
        failures.append(f"dem_filled lowers terrain by {-diff.min():.3f}m somewhere")
    if diff.max() == 0:
        failures.append("dem_filled identical to input — no depressions filled (suspicious)")

    # D8 pointer codes: powers of two 1..128, plus 0 for undefined.
    flow_dir = np.unique(_read_valid(FLOW_DIR))
    legal = {0, 1, 2, 4, 8, 16, 32, 64, 128}
    illegal = set(flow_dir.tolist()) - legal
    if illegal:
        failures.append(f"flow_dir contains non-D8 values: {sorted(illegal)[:5]}")

    # Accumulation in cells: every cell counts itself; max bounded by cell count.
    flow_acc = _read_valid(FLOW_ACC)
    n_cells = flow_acc.size
    if flow_acc.min() < 1:
        failures.append(f"flow_acc min {flow_acc.min():.2f} < 1 cell")
    if flow_acc.max() > n_cells:
        failures.append(f"flow_acc max {flow_acc.max():.0f} exceeds cell count {n_cells}")
    if flow_acc.max() < 100:
        failures.append("flow_acc max < 100 cells — drainage network failed to form")

    # Rainfall artifacts.
    import json

    if not RAINFALL_SAMPLE.exists():
        failures.append(f"missing output: {RAINFALL_SAMPLE.relative_to(ROOT)}")
    else:
        import pandas as pd

        rain = pd.read_csv(RAINFALL_SAMPLE)["rain_mm"].dropna()
        if len(rain) < 300:
            failures.append(f"rainfall sample has only {len(rain)} valid days")
        if rain.min() < 0 or rain.max() > 500:
            failures.append(f"rainfall outside [0, 500] mm: {rain.min():.1f}..{rain.max():.1f}")

    if not SCENARIOS.exists():
        failures.append(f"missing output: {SCENARIOS.relative_to(ROOT)}")
    else:
        try:
            payload = json.loads(SCENARIOS.read_text())
            for s in payload["scenarios"]:
                if not {"name", "rainfall_mm", "description"} <= set(s):
                    failures.append(f"scenario missing keys: {s}")
                elif not 0 < s["rainfall_mm"] <= 500:
                    failures.append(f"scenario {s['name']} rainfall {s['rainfall_mm']} implausible")
        except (json.JSONDecodeError, KeyError) as exc:
            failures.append(f"scenarios.json malformed: {exc}")

    # Depth rasters: contract compliance + physical plausibility.
    # Known simplification: depth is capped at local depression storage; real
    # spillover routing between depressions is not modeled (Phase 2a proxy).
    if SCENARIOS.exists():
        with rasterio.open(DEM_REPROJECTED) as ref:
            ref_crs, ref_shape, ref_transform = ref.crs, ref.shape, ref.transform
            ground = ref.read(1, masked=True)
        with rasterio.open(DEM_FILLED) as f:
            storage = np.ma.clip(f.read(1, masked=True) - ground, 0, None).filled(0)

        for s in json.loads(SCENARIOS.read_text())["scenarios"]:
            path = PROCESSED / f"depth_{s['name']}.tif"
            if not path.exists():
                failures.append(f"missing output: {path.relative_to(ROOT)}")
                continue
            with rasterio.open(path) as src:
                if src.crs != ref_crs or src.shape != ref_shape or src.transform != ref_transform:
                    failures.append(f"{path.name}: grid/CRS mismatch with dem_reprojected")
                    continue
                depth = src.read(1, masked=True)
            d = depth.filled(0)
            if d.min() < 0:
                failures.append(f"{path.name}: negative depth {d.min():.3f} m")
            if (d - storage).max() > 0.001:
                failures.append(
                    f"{path.name}: depth exceeds depression storage by "
                    f"{(d - storage).max():.3f} m"
                )

    # Web export: all files present, under the frontend size budget.
    web_meta = export.WEB_DIR / "web_meta.json"
    if not web_meta.exists():
        failures.append(f"missing output: {web_meta.relative_to(ROOT)}")
    else:
        try:
            meta = json.loads(web_meta.read_text())
            expected_bytes = meta["width"] * meta["height"] * 2
            for m in meta["scenarios"]:
                f = export.WEB_DIR / m["file"]
                if not f.exists():
                    failures.append(f"missing output: {f.relative_to(ROOT)}")
                elif f.stat().st_size != expected_bytes:
                    failures.append(
                        f"{f.name}: {f.stat().st_size} bytes, expected {expected_bytes}"
                    )
                elif f.stat().st_size > 3 * 1024 * 1024:
                    failures.append(f"{f.name} exceeds 3 MB frontend budget")
        except (json.JSONDecodeError, KeyError) as exc:
            failures.append(f"web_meta.json malformed: {exc}")

    # Engine: interpolated queries plausible and monotonic in rainfall.
    prev_volume = -1.0
    for mm in (0, 75, 125, 200, 300, 500):
        grid = engine.get_flood_state(mm)
        wet = grid[grid != engine.NODATA]
        if wet.min() < 0:
            failures.append(f"engine({mm}mm): negative depth {wet.min():.3f}")
        volume = float(wet.sum())
        if volume < prev_volume - 0.001:
            failures.append(f"engine({mm}mm): flooded volume decreased vs previous query")
        prev_volume = volume
    if float(engine.get_flood_state(0).max()) > 0:
        failures.append("engine(0mm): expected fully dry grid")

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
    terrain.fill_depressions(DEM_REPROJECTED, DEM_FILLED)
    terrain.compute_flow_direction(DEM_FILLED, FLOW_DIR)
    terrain.compute_flow_accumulation(DEM_FILLED, FLOW_ACC)

    df = rainfall.fetch_rainfall(RAINFALL_YEAR)
    rainfall.save_sample(df)
    rainfall.build_design_storms()

    proxy.simulate_all()
    export.export_web()

    failures = sanity_checks()
    if failures:
        for f in failures:
            logger.error("SANITY FAIL: %s", f)
        return 1

    logger.info("All outputs written to %s — sanity checks passed.", PROCESSED.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
