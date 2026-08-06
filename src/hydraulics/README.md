# Hydraulics: depth-raster output contract

Any flood-depth producer in this project — today the fill-and-spill proxy
(`proxy.py`), later the Track B HEC-RAS adapter (`hecras_adapter.py`) — must
emit exactly this format. The simulation engine and frontend consume only
this contract and never care which model generated the data. This is what
makes the proxy → HEC-RAS upgrade a substitution, not a rebuild.

## Contract

| Property   | Value                                                       |
|------------|-------------------------------------------------------------|
| File       | `data/processed/depth_<scenario_name>.tif`                  |
| Format     | single-band GeoTIFF, float32                                |
| Grid/CRS   | identical to `data/processed/dem_reprojected.tif` (EPSG:32644, ~30 m cells) |
| Units      | meters of standing water depth                              |
| Range      | `>= 0` on valid cells; `0` = dry                            |
| Nodata     | `-9999`                                                     |
| Scenarios  | one file per entry in `data/processed/scenarios.json`       |

## What the current proxy does

Fill-and-spill depression flooding: effective water volume
(`rainfall_mm x runoff_coeff x zone area`) is poured into DEM depressions by
elevation priority — a global water level is raised until the stored volume
matches, each cell capped at its depression storage depth
(`dem_filled - dem_reprojected`). Lowest terrain floods first.

## What the proxy does NOT model — intentional MVP scope, not oversight

- **Overland flow between depressions.** Water appears directly in
  depressions; it does not travel across the surface to reach them, and a
  depression's overflow is not routed downstream to the next one. Excess
  volume beyond total depression capacity is assumed to leave the zone.
- **Time dynamics.** One static equilibrium per scenario; no hydrograph, no
  filling/draining over hours.
- **Drainage infrastructure.** No storm drains, culverts, pumps, or channel
  capacity. The runoff coefficient is the only knob approximating "how much
  water the surface sheds", and per-depression water conservation is
  approximated by the single global level.

All of the above is what HEC-RAS 2D (Track B) adds. Until then, outputs are
indicative — "where pools first, relatively how deep" — not engineering-grade
depths.
