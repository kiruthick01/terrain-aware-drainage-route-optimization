"""Land use / land cover: OSM features classified for Manning's n and SCS
Curve Number, on the same grid as dem_reprojected.tif.

Track B (HEC-RAS) needs two things Phase 1's terrain pipeline doesn't
produce: surface roughness (Manning's n) and infiltration losses (SCS Curve
Number), both spatially varying. Both derive from one land-use
classification, so a single OSM fetch + raster serves both RAS Mapper
layers -- Land Cover (roughness table) and the Curve Number loss raster.

Classification (priority low -> high; rasterize burns shapes in list order
and later shapes win on overlap, so small precise features like buildings
correctly override broad landuse polygons underneath them):
    1 vegetation    landuse=forest/farmland/grass/meadow/orchard/allotments,
                     leisure=park/garden/pitch/golf_course,
                     natural=wood/grassland/scrub
    2 water         natural=water, waterway=*
    3 paved         highway=* (roads/paths). OSM highways are centerlines,
                     not footprints -- buffered ~4m (approx local road
                     half-width) before rasterizing or a line this thin
                     barely burns any cells.
    4 building      building=* (roofs; drawn last, wins on overlap)
    5 unclassified  default fill for cells with no matching OSM tag.
                     Velachery is dense urban with patchy OSM coverage;
                     defaulting to "open ground" would understate
                     imperviousness, so the default represents a generic
                     urban-mix condition instead -- a documented
                     limitation, not an OSM data gap left unfixed.

Manning's n and Curve Number values below are standard published ranges
(Chow 1959 urban n; NRCS TR-55 CN table), not measured for this site. Curve
Numbers assume Hydrologic Soil Group D (poorest infiltration) throughout --
no soil survey data exists for this zone; Group D is the conservative match
for Velachery's known drainage problems (the reason the zone was picked in
the first place). Stated here alongside the proxy's own caveats
(src/hydraulics/README.md), same honesty pattern, not an oversight.

Usage:
    python -m src.pipeline.landuse    # fetch -> rasterize -> curve number -> table
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
import rasterio
from rasterio.features import rasterize

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

BOUNDARY = RAW / "zone_boundary.geojson"
DEM_REPROJECTED = PROCESSED / "dem_reprojected.tif"
OSM_LANDUSE = RAW / "osm_landuse.geojson"
LANDUSE_TIF = PROCESSED / "landuse.tif"
CURVE_NUMBER_TIF = PROCESSED / "curve_number.tif"
CLASSES_CSV = PROCESSED / "landuse_classes.csv"

NODATA = -9999.0  # curve_number.tif (float); matches the rest of the pipeline
NODATA_CLASS = 0  # landuse.tif (uint8 categorical): outside the valid DEM mask
DEFAULT_CLASS = 5  # unclassified_urban_mix: in-zone cells with no OSM match
ROAD_BUFFER_M = 4.0

# class_value -> (name, manning_n, curve_number). Order matters: this is the
# rasterize priority (low -> high), see module docstring.
CLASSES = {
    1: ("vegetation", 0.035, 80),
    2: ("water", 0.030, 98),
    3: ("paved", 0.013, 98),
    4: ("building", 0.015, 95),
    5: ("unclassified_urban_mix", 0.025, 90),
}

OSM_TAG_QUERIES = {
    1: {
        "landuse": ["forest", "farmland", "grass", "meadow", "orchard", "allotments"],
        "leisure": ["park", "garden", "pitch", "golf_course"],
        "natural": ["wood", "grassland", "scrub"],
    },
    2: {"natural": ["water"], "waterway": True},
    3: {"highway": True},
    4: {"building": True},
}


def fetch_landuse(boundary_path: Path = BOUNDARY, out_path: Path = OSM_LANDUSE) -> gpd.GeoDataFrame:
    """Fetch OSM features within the zone boundary, tagged with class_value.

    One Overpass query per class (see OSM_TAG_QUERIES) rather than a single
    combined query, since each class's tags overlap on keys like `landuse`
    and mixing them would blur the classification. Network required.
    """
    boundary = gpd.read_file(boundary_path)
    polygon = boundary.union_all()

    frames = []
    for class_value, tags in OSM_TAG_QUERIES.items():
        name = CLASSES[class_value][0]
        try:
            gdf = ox.features_from_polygon(polygon, tags)
        except ox._errors.InsufficientResponseError:
            gdf = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        if gdf.empty:
            logger.warning("no OSM features for class %d (%s), tags=%s", class_value, name, tags)
            continue
        gdf = gdf[["geometry"]].copy()
        gdf["class_value"] = class_value
        frames.append(gdf)
        logger.info("class %d (%s): %d features", class_value, name, len(gdf))

    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_file(out_path, driver="GeoJSON")
    logger.info("OSM land use written -> %s (%d features total)", out_path.name, len(combined))
    return combined


def rasterize_landuse(
    features: gpd.GeoDataFrame | None = None,
    dem_path: Path = DEM_REPROJECTED,
    out_path: Path = LANDUSE_TIF,
) -> Path:
    """Burn classified OSM features onto the dem_reprojected.tif grid.

    Priority follows CLASSES iteration order (vegetation first, building
    last -- see module docstring); cells outside the valid DEM mask get
    NODATA_CLASS, in-zone cells with no match get DEFAULT_CLASS.
    """
    if features is None:
        features = gpd.read_file(OSM_LANDUSE)

    with rasterio.open(dem_path) as ref:
        transform, shape, crs, profile = ref.transform, ref.shape, ref.crs, ref.profile.copy()
        valid = ref.read_masks(1) > 0

    proj = features.to_crs(crs)
    roads = proj["class_value"] == 3
    proj.loc[roads, "geometry"] = proj.loc[roads, "geometry"].buffer(ROAD_BUFFER_M)

    shapes = [
        (geom, class_value)
        for geom, class_value in zip(proj.geometry, proj["class_value"])
        if geom is not None and not geom.is_empty
    ]

    burned = rasterize(
        shapes, out_shape=shape, transform=transform,
        fill=DEFAULT_CLASS, all_touched=True, dtype="uint8",
    )
    burned[~valid] = NODATA_CLASS

    profile.update(dtype="uint8", nodata=NODATA_CLASS, count=1)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(burned, 1)

    counts = {CLASSES.get(v, ("nodata",))[0]: int((burned == v).sum()) for v in np.unique(burned)}
    logger.info("Land use classes written -> %s: %s", out_path.name, counts)
    return out_path


def build_curve_number(landuse_path: Path = LANDUSE_TIF, out_path: Path = CURVE_NUMBER_TIF) -> Path:
    """Map land-use class -> SCS Curve Number (Hydrologic Soil Group D
    throughout -- see module docstring for why)."""
    with rasterio.open(landuse_path) as src:
        classes = src.read(1)
        profile = src.profile.copy()

    cn = np.full(classes.shape, NODATA, dtype="float32")
    for value, (_name, _n, curve_number) in CLASSES.items():
        cn[classes == value] = curve_number

    profile.update(dtype="float32", nodata=NODATA)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(cn, 1)

    valid_cn = cn[cn != NODATA]
    logger.info(
        "Curve number raster written -> %s (range %.0f-%.0f, mean %.1f)",
        out_path.name, valid_cn.min(), valid_cn.max(), valid_cn.mean(),
    )
    return out_path


def amc_curve_number(cn2: np.ndarray, amc: str) -> np.ndarray:
    """Convert a normal-condition (AMC-II) Curve Number to AMC-I (dry) or
    AMC-III (wet) -- the standard NRCS antecedent-moisture adjustment
    (Mockus 1964; widely reproduced, e.g. NEH630 Ch.10 eq. 10-11/10-12).
    Unlike the Type II storm shape (see hyetograph.py), these are simple
    closed-form formulas, not a table -- no sourcing/verification risk."""
    if amc == "dry":
        return 4.2 * cn2 / (10 - 0.058 * cn2)
    if amc == "wet":
        return 23 * cn2 / (10 + 0.13 * cn2)
    raise ValueError(f"amc must be 'dry' or 'wet', got {amc!r}")


def build_curve_number_amc(
    cn2_path: Path = CURVE_NUMBER_TIF, out_dir: Path = PROCESSED
) -> dict[str, Path]:
    """Derive AMC-I (dry) and AMC-III (wet) Curve Number rasters from the
    AMC-II (normal) raster built by build_curve_number(). Track B precomputes
    3 antecedent-moisture classes per rainfall scenario (ROADMAP.md Phase
    2b) -- these are the other two; the hyetograph itself doesn't change
    with AMC, only this loss layer does."""
    with rasterio.open(cn2_path) as src:
        cn2 = src.read(1)
        profile = src.profile.copy()

    valid = cn2 != NODATA
    out = {}
    for amc in ("dry", "wet"):
        cn = np.full(cn2.shape, NODATA, dtype="float32")
        cn[valid] = amc_curve_number(cn2[valid], amc)
        path = out_dir / f"curve_number_{amc}.tif"
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(cn, 1)
        logger.info(
            "Curve number (%s) written -> %s (range %.0f-%.0f)",
            amc, path.name, cn[valid].min(), cn[valid].max(),
        )
        out[amc] = path
    return out


def write_classes_table(out_path: Path = CLASSES_CSV) -> Path:
    """Class lookup table: RAS Mapper's Land Cover Manager imports the
    (class_value, manning_n) columns directly; curve_number is kept
    alongside as the human-readable reference for curve_number.tif."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["class_value", "name", "manning_n", "curve_number"])
        for value, (name, n, cn) in sorted(CLASSES.items()):
            writer.writerow([value, name, n, cn])
    logger.info("Land use class table written -> %s", out_path.name)
    return out_path


def build_all() -> None:
    features = fetch_landuse()
    rasterize_landuse(features)
    build_curve_number()
    build_curve_number_amc()
    write_classes_table()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build_all()
