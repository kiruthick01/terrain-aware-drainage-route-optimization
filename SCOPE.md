# Project Scope

## MVP definition

A shareable web dashboard where a user picks a rainfall scenario for one
Chennai zone (Velachery) and sees flood extent/depth update in near-real-time,
backed by a documented, reproducible data pipeline.

Success looks like: a URL anyone can open, a rainfall slider, and a flood-depth
layer over a real Chennai neighborhood that responds in under a second.

## Non-goals (explicitly out of scope for MVP)

- **No drainage-network engineering design** — this tool analyzes flood risk;
  it does not size pipes, design culverts, or propose infrastructure.
- **No real-time sensor or live weather data** — scenarios are precomputed
  design storms, not live feeds.
- **No multi-city support until Phase 6** — Velachery first. Generalization
  comes only after one zone works end-to-end.
- **No hydraulic calibration claims** — until Track B (real HEC-RAS), outputs
  are indicative, not engineering-grade.

## Known limitations

1. **Proxy hydraulics (until Track B).** Flood depths come from a simplified
   fill-and-spill depression model, not a real 2D hydraulic solver. Good for
   relative "where pools first" insight; not for absolute depth accuracy.
   Swapped for HEC-RAS 2D output in Track B via a fixed output contract.
2. **Coarse rainfall grid.** IMD gridded rainfall is 0.25° (~27 km) — the
   entire study zone sits inside roughly one grid cell. Fine for zone-wide
   scenario totals; useless for intra-zone rainfall variation.
3. **30 m DEM.** SRTM resolution smooths out streets, small channels, and
   micro-topography. Underpasses and narrow drains are invisible at this scale.
4. **DEM noise near water.** Source DEM reports elevations down to -6 m near
   water bodies — SRTM artifacts, not real bathymetry. Handled during
   hydrological conditioning, logged here as a data-quality caveat.
5. **No zone polygon yet.** Until `data/raw/zone_boundary.geojson` is drawn
   (QGIS step pending), the pipeline processes the full downloaded DEM tile
   rather than a refined study-area boundary.
