"""Generate data/raw/zone_boundary.geojson as a rectangle of the DEM's extent.

MVP stand-in for a hand-drawn study-area polygon: the "zone" is simply the
full DEM footprint, so clipping is exercised end-to-end but removes nothing.
Refine later by replacing the GeoJSON with a tighter polygon (QGIS or edits
here) — the pipeline picks up whatever geometry the file contains.

Usage:
    python -m src.pipeline.make_zone_boundary
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pipeline.make_zone_boundary")

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "data" / "raw" / "zone_boundary.geojson"

# DEM extent in EPSG:4326 (from data/raw/chennai_velachery_dem.tif bounds).
LEFT = 80.18847222225668
BOTTOM = 12.948194444438208
RIGHT = 80.25791666670114
TOP = 13.00013888888266


def main() -> None:
    zone = box(LEFT, BOTTOM, RIGHT, TOP)
    gdf = gpd.GeoDataFrame(
        {"name": ["velachery_mvp_zone"]}, geometry=[zone], crs="EPSG:4326"
    )
    gdf.to_file(OUT_PATH, driver="GeoJSON")
    logger.info("Zone boundary written -> %s", OUT_PATH.relative_to(ROOT))


if __name__ == "__main__":
    main()
