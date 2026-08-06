"""Terrain processing: load, clip, reproject, and derive slope/aspect from a DEM.

Pipeline order matters:
    load -> clip -> reproject -> slope/aspect
Clip happens in geographic coords (boundary GeoJSON is drawn in EPSG:4326);
slope/aspect require a projected CRS so cell units are meters.
"""

from __future__ import annotations

import logging
from pathlib import Path

import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject
import whitebox

logger = logging.getLogger(__name__)

# UTM zone 44N — covers Chennai; coordinates are meters east/north.
TARGET_CRS = "EPSG:32644"
NODATA = -9999.0


def load_dem(path: str | Path) -> rasterio.DatasetReader:
    """Open a DEM and validate it is usable before any processing.

    Returns an open rasterio dataset; caller is responsible for closing it
    (or using it as a context manager).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"DEM not found: {path}")

    dem = rasterio.open(path)

    if dem.crs is None:
        dem.close()
        raise ValueError(f"DEM has no CRS defined: {path}")
    if dem.count != 1:
        dem.close()
        raise ValueError(f"Expected single-band DEM, got {dem.count} bands: {path}")
    if dem.width == 0 or dem.height == 0:
        dem.close()
        raise ValueError(f"DEM has empty dimensions: {path}")

    logger.info(
        "Loaded DEM %s: %dx%d cells, CRS %s, bounds %s",
        path.name, dem.width, dem.height, dem.crs, tuple(round(b, 4) for b in dem.bounds),
    )
    return dem


def clip_dem(
    src_path: str | Path,
    dst_path: str | Path,
    boundary_path: str | Path | None = None,
) -> Path:
    """Clip the DEM to a study-area boundary polygon.

    boundary_path: GeoJSON polygon (data/raw/zone_boundary.geojson once drawn).
    Until that file exists, pass None: the DEM is copied through unchanged so
    the rest of the pipeline is unaffected when clipping arrives.
    """
    src_path, dst_path = Path(src_path), Path(dst_path)

    if boundary_path is None:
        logger.warning(
            "No zone boundary provided — passing full DEM through unclipped. "
            "Draw data/raw/zone_boundary.geojson to enable clipping."
        )
        with rasterio.open(src_path) as src:
            profile = src.profile
            data = src.read(1)
        with rasterio.open(dst_path, "w", **profile) as dst:
            dst.write(data, 1)
        return dst_path

    import geopandas as gpd
    from rasterio.mask import mask as rio_mask

    boundary = gpd.read_file(boundary_path)
    with rasterio.open(src_path) as src:
        # Boundary must be in the same CRS as the raster before masking.
        boundary = boundary.to_crs(src.crs)
        clipped, transform = rio_mask(src, boundary.geometry, crop=True, nodata=NODATA)
        profile = src.profile
        profile.update(
            height=clipped.shape[1],
            width=clipped.shape[2],
            transform=transform,
            nodata=NODATA,
        )
    with rasterio.open(dst_path, "w", **profile) as dst:
        dst.write(clipped)
    logger.info("Clipped DEM to %s -> %s", boundary_path, dst_path)
    return dst_path


def reproject_dem(src_path: str | Path, dst_path: str | Path) -> Path:
    """Reproject the DEM from geographic coords (degrees) to UTM 44N (meters).

    Slope and flow math need horizontal distance in the same unit as elevation.
    Bilinear resampling: each output cell's elevation is a distance-weighted
    average of the 4 nearest input cells — appropriate for continuous surfaces
    like terrain (never use it for categorical rasters).
    """
    src_path, dst_path = Path(src_path), Path(dst_path)

    with rasterio.open(src_path) as src:
        # Compute the shape/affine transform of the output grid in the target
        # CRS that best matches the source's resolution and extent.
        transform, width, height = calculate_default_transform(
            src.crs, TARGET_CRS, src.width, src.height, *src.bounds
        )
        profile = src.profile.copy()
        profile.update(
            crs=TARGET_CRS,
            transform=transform,
            width=width,
            height=height,
            nodata=NODATA,
            dtype="float32",
        )

        with rasterio.open(dst_path, "w", **profile) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=TARGET_CRS,
                src_nodata=src.nodata,
                dst_nodata=NODATA,
                resampling=Resampling.bilinear,
            )

    with rasterio.open(dst_path) as check:
        res = check.res
    logger.info(
        "Reprojected %s -> %s (%s, cell size %.1fm x %.1fm)",
        src_path.name, dst_path.name, TARGET_CRS, res[0], res[1],
    )
    return dst_path


def _wbt() -> whitebox.WhiteboxTools:
    wbt = whitebox.WhiteboxTools()
    wbt.verbose = False
    return wbt


def compute_slope(dem_path: str | Path, out_path: str | Path) -> Path:
    """Slope in degrees via WhiteboxTools (Horn's method on a 3x3 window).

    For each cell: dz/dx and dz/dy from the 8 neighbors, then
    slope = arctan(sqrt((dz/dx)^2 + (dz/dy)^2)). Requires a projected DEM.
    """
    dem_path, out_path = Path(dem_path).resolve(), Path(out_path).resolve()
    ret = _wbt().slope(str(dem_path), str(out_path), units="degrees")
    if ret != 0 or not out_path.exists():
        raise RuntimeError(f"WhiteboxTools slope failed (exit {ret}) for {dem_path}")
    logger.info("Slope written -> %s", out_path.name)
    return out_path


def compute_aspect(dem_path: str | Path, out_path: str | Path) -> Path:
    """Aspect: compass direction each cell faces, degrees clockwise from north.

    Same gradient stencil as slope, but the angle of steepest descent instead
    of its magnitude: 0=N, 90=E, 180=S, 270=W. Flat cells get -9999 nodata.
    """
    dem_path, out_path = Path(dem_path).resolve(), Path(out_path).resolve()
    ret = _wbt().aspect(str(dem_path), str(out_path))
    if ret != 0 or not out_path.exists():
        raise RuntimeError(f"WhiteboxTools aspect failed (exit {ret}) for {dem_path}")
    logger.info("Aspect written -> %s", out_path.name)
    return out_path
