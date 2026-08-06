"""Export depth rasters to the web format consumed by the Phase 5 frontend.

Per scenario: reproject depth from UTM 44N to EPSG:4326 (so the grid drapes
on a web map without skew), quantize to uint16 millimeters, write raw
little-endian binary. One shared web_meta.json describes grid, bounds, and
scenario list. Format spec + JS decode: src/simulation/README.md.

Nearest-neighbor resampling on purpose: bilinear would smear values across
the nodata boundary and invent depths; nearest keeps every exported value an
exact proxy output.

Usage:
    python -m src.simulation.export
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
WEB_DIR = PROCESSED / "web"
SCENARIOS_JSON = PROCESSED / "scenarios.json"

NODATA = -9999.0
WEB_CRS = "EPSG:4326"
U16_NODATA = 65535  # sentinel in exported uint16 grids (= 65.535 m, unreachable)


def export_web(out_dir: Path = WEB_DIR) -> Path:
    """Write depth_<name>.bin per scenario + web_meta.json. Returns meta path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(SCENARIOS_JSON.read_text())
    scenarios = sorted(payload["scenarios"], key=lambda s: s["rainfall_mm"])

    # One shared target grid computed from the first raster; all scenarios
    # come from the same source grid, so it applies to every one of them.
    first = PROCESSED / f"depth_{scenarios[0]['name']}.tif"
    with rasterio.open(first) as src:
        transform, width, height = calculate_default_transform(
            src.crs, WEB_CRS, src.width, src.height, *src.bounds
        )

    meta_scenarios = []
    for s in scenarios:
        src_path = PROCESSED / f"depth_{s['name']}.tif"
        dst = np.full((height, width), NODATA, dtype="float32")
        with rasterio.open(src_path) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=dst,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=WEB_CRS,
                src_nodata=NODATA,
                dst_nodata=NODATA,
                resampling=Resampling.nearest,
            )

        mm = np.round(dst * 1000.0)
        grid = np.where(dst == NODATA, U16_NODATA, np.clip(mm, 0, U16_NODATA - 1))
        grid = grid.astype("<u2")  # uint16 little-endian, row-major, top-left origin

        bin_path = out_dir / f"depth_{s['name']}.bin"
        bin_path.write_bytes(grid.tobytes())
        max_mm = int(grid[grid != U16_NODATA].max()) if (grid != U16_NODATA).any() else 0
        meta_scenarios.append(
            {
                "name": s["name"],
                "rainfall_mm": s["rainfall_mm"],
                "file": bin_path.name,
                "max_depth_mm": max_mm,
            }
        )
        logger.info(
            "%s -> %s (%.0f KB, max depth %.2f m)",
            src_path.name, bin_path.name, bin_path.stat().st_size / 1024, max_mm / 1000,
        )

    # Affine for a north-up EPSG:4326 grid: west/north at c/f, pixel size a/e.
    west, north = transform.c, transform.f
    east = west + transform.a * width
    south = north + transform.e * height  # e is negative (rows go south)

    meta = {
        "version": 1,
        "crs": WEB_CRS,
        "width": width,
        "height": height,
        "bounds": {"west": west, "south": south, "east": east, "north": north},
        "units": "mm",
        "dtype": "uint16",
        "endianness": "little",
        "order": "row-major, row 0 = northernmost",
        "nodata": U16_NODATA,
        "base_runoff_coeff": 0.75,
        "scenarios": meta_scenarios,
    }
    meta_path = out_dir / "web_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    total_kb = sum((out_dir / m["file"]).stat().st_size for m in meta_scenarios) / 1024
    logger.info(
        "web_meta.json written; %d scenarios, %.0f KB total, grid %dx%d",
        len(meta_scenarios), total_kb, width, height,
    )
    return meta_path


if __name__ == "__main__":
    export_web()
