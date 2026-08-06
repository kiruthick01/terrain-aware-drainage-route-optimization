"""Rainfall processing: IMD gridded daily rain + design-storm scenarios.

Grid-resolution reality: IMD daily rainfall is 0.25 deg (~27 km) — the whole
study zone fits inside a single grid cell, and that cell is nodata (-999)
because IMD's land mask calls this coastal sliver sea. We therefore read the
nearest *valid land* cell (~20 km west) and treat its value as zone-uniform
rainfall. No intra-zone rainfall variation exists at this resolution; logged
as a known limitation in SCOPE.md. Scenario totals are what matter for the MVP.

2015 ground truth from this data (cell 13.0N, 80.0E): the famous Dec 1 event
appears as 349.6 mm on Dec 2 (IMD's 0830-0830 IST recording window shifts
daily totals one day late); Nov 16 was 263.1 mm; November 2015 total 1163 mm.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
IMD_DIR = ROOT / "data" / "raw" / "imd"
SAMPLE_CSV = ROOT / "data" / "raw" / "rainfall_2015_sample.csv"
SCENARIOS_JSON = ROOT / "data" / "processed" / "scenarios.json"

# Zone bbox (same as DEM bounds), EPSG:4326.
ZONE_BBOX = {
    "left": 80.18847222225668,
    "bottom": 12.948194444438208,
    "right": 80.25791666670114,
    "top": 13.00013888888266,
}

IMD_NODATA = -999.0


def fetch_rainfall(year: int, bbox: dict | None = None) -> pd.DataFrame:
    """Daily rainfall (mm) for one year over the zone, as a DataFrame.

    Reads the IMD yearwise .grd from data/raw/imd if already downloaded,
    otherwise downloads it (network required, ~50 MB per year all-India).

    Selection: cells intersecting bbox; if all are nodata (our case — the
    zone's cell is sea-masked), falls back to the nearest valid land cell
    and records which cell was used in the DataFrame attrs.
    """
    import imdlib

    bbox = bbox or ZONE_BBOX
    IMD_DIR.mkdir(parents=True, exist_ok=True)

    grd = IMD_DIR / "rain" / f"{year}.grd"
    if grd.exists():
        data = imdlib.open_data("rain", year, year, "yearwise", str(IMD_DIR))
    else:
        logger.info("IMD %d not cached — downloading (~50 MB)", year)
        data = imdlib.get_data("rain", year, year, "yearwise", str(IMD_DIR))

    ds = data.get_xarray()
    rain = ds["rain"]

    # Try the cells covering the bbox first.
    sub = rain.sel(
        lat=slice(bbox["bottom"], bbox["top"]),
        lon=slice(bbox["left"], bbox["right"]),
    )
    zone_valid = sub.where(sub != IMD_NODATA).count() > 0

    if zone_valid:
        series = sub.where(sub != IMD_NODATA).mean(dim=["lat", "lon"])
        cell = "bbox mean"
    else:
        # Zone cell is sea-masked: nearest valid land cell by distance.
        dec_mean = rain.where(rain != IMD_NODATA).mean(dim="time")
        valid = dec_mean.to_dataframe(name="mean_rain").dropna().reset_index()
        cy = (bbox["top"] + bbox["bottom"]) / 2
        cx = (bbox["left"] + bbox["right"]) / 2
        dist2 = (valid["lat"] - cy) ** 2 + (valid["lon"] - cx) ** 2
        nearest = valid.loc[dist2.idxmin()]
        series = rain.sel(lat=nearest["lat"], lon=nearest["lon"])
        cell = f"nearest land cell ({nearest['lat']:.2f}N, {nearest['lon']:.2f}E)"
        logger.warning(
            "Zone's IMD cell is sea-masked (nodata); using %s ~%.0f km from zone center",
            cell, np.sqrt(float(dist2.min())) * 111,
        )

    df = pd.DataFrame(
        {
            "date": pd.to_datetime(series["time"].values),
            "rain_mm": np.asarray(series.values, dtype=float),
        }
    )
    df.loc[df["rain_mm"] == IMD_NODATA, "rain_mm"] = np.nan
    df.attrs["source_cell"] = cell
    df.attrs["year"] = year
    logger.info(
        "Rainfall %d loaded from %s: %d days, max %.1f mm, total %.0f mm",
        year, cell, len(df), df["rain_mm"].max(), df["rain_mm"].sum(),
    )
    return df


def save_sample(df: pd.DataFrame, path: Path = SAMPLE_CSV) -> Path:
    """Persist the fetched year as CSV (Phase 0.2 artifact)."""
    df.to_csv(path, index=False)
    logger.info("Rainfall sample written -> %s", path.name)
    return path


def build_design_storms(out_path: Path = SCENARIOS_JSON) -> Path:
    """Write the scenario contract consumed by the Phase 2a proxy model.

    rainfall_mm is a per-day storm total applied uniformly over the zone.
    Magnitudes anchored to the 2015 IMD record at the nearest land cell.
    """
    scenarios = [
        {
            "name": "moderate",
            "rainfall_mm": 50,
            "description": "Heavy monsoon day; roughly monthly occurrence in NE monsoon.",
        },
        {
            "name": "heavy",
            "rainfall_mm": 100,
            "description": "Very heavy rainfall day (IMD 'very heavy' threshold is 115.6 mm).",
        },
        {
            "name": "severe",
            "rainfall_mm": 150,
            "description": "Severe event; between 2015's Nov 9 (164 mm) and Nov 13 (120 mm) days.",
        },
        {
            "name": "extreme",
            "rainfall_mm": 250,
            "description": "Nov 16 2015-class event (263 mm observed at reference cell).",
        },
        {
            "name": "extreme_2015_peak",
            "rainfall_mm": 350,
            "description": "Dec 1-2 2015 flood peak (349.6 mm observed at reference cell).",
        },
    ]
    payload = {
        "version": 1,
        "units": "mm_per_day",
        "applied_as": "uniform depth over zone",
        "reference": "IMD 0.25deg daily grid, cell 13.00N 80.00E, year 2015",
        "scenarios": scenarios,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    logger.info("Design storms written -> %s (%d scenarios)", out_path.name, len(scenarios))
    return out_path
