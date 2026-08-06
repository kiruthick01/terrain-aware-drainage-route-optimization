# Project Roadmap — terrain-aware-drainage-route-optimization

> Interactive flood-risk analysis and "what-if" scenario simulation for
> flood-prone zones in Chennai (initially Velachery / Mudichur), expanding to
> other Indian cities. Fully self-built, portfolio-grade.

---

## Strategy: Two-Track Build

- **Track A (now, Mac):** Full pipeline + prototype using a simplified hydraulic
  proxy. Proves architecture, what-if engine, and frontend end-to-end.
- **Track B (later, Windows):** Swap proxy for real HEC-RAS 2D output.
  Substitution, not rebuild — everything in Track A is designed swap-ready.

**Definition of done (MVP):** A shareable web dashboard where a user picks a
rainfall scenario for one Chennai zone and sees flood extent/depth update in
near-real-time, backed by a documented, reproducible data pipeline.

---

## Target Repo Structure
terrain-aware-drainage-route-optimization/
├── data/
│ ├── raw/ # untouched downloads (gitignored)
│ ├── processed/ # pipeline outputs (gitignored, reproducible)
│ └── README.md # data sources, download instructions, licenses
├── src/
│ ├── pipeline/ # Phase 1: terrain + rainfall processing
│ ├── hydraulics/ # Phase 2a proxy now, 2b adapter later
│ ├── simulation/ # Phase 4: what-if engine
│ └── utils/
├── frontend/ # Phase 5: dashboard app
├── notebooks/ # exploration only, never production logic
├── devlog/
├── SCOPE.md
├── ROADMAP.md
└── README.md

---

## Phase 0 — Foundations & Scoping  [Track A — ~1–2 days remaining]

### 0.1 Zone lock-in
- [ ] In QGIS, overlay `output_hh.tif` on OSM basemap (XYZ layer)
- [ ] Draw exact study-area polygon (QGIS: new GeoPackage layer → polygon)
      covering Velachery + immediate drainage context (~5–10 km²)
- [ ] Export polygon as `data/raw/zone_boundary.geojson`
- [ ] Rename DEM → `data/raw/chennai_velachery_dem.tif`

### 0.2 Rainfall data proof
- [ ] `pip install imdlib` on Mac
- [ ] Pull 2015 gridded daily rainfall (the Chennai flood year)
- [ ] Extract the grid cell(s) covering the zone; save sample as
      `data/raw/rainfall_2015_sample.csv`
- [ ] Note grid resolution limitation (0.25° ≈ 27 km — coarse; fine for MVP,
      log as known limitation)

### 0.3 Scope definition
- [ ] Write `SCOPE.md`: MVP definition (above), explicit non-goals
      (no drainage-network engineering design, no real-time sensor data,
      no multi-city until Phase 6), known limitations (proxy hydraulics
      until Track B, coarse rainfall grid, 30m DEM)

**Exit criteria:** zone polygon + renamed DEM + rainfall sample in repo,
SCOPE.md written, all committed.

---

## Phase 1 — Data Pipeline  [Track A — ~4–6 days]

### 1.1 Environment (half day)
- [ ] `python -m venv .venv` + `requirements.txt`:
      rasterio, geopandas, numpy, matplotlib, pyproj, shapely, imdlib,
      whitebox (or richdem)
- [ ] Verify all imports work on macOS (GDAL wheels via rasterio should be
      fine; log any workarounds in devlog)

### 1.2 Terrain module — `src/pipeline/terrain.py` (2 days)
- [ ] `load_dem(path) -> rasterio dataset` with CRS validation
- [ ] `clip_dem(dem, boundary_geojson) -> clipped GeoTIFF`
      → output `data/processed/dem_clipped.tif`
- [ ] Reproject to a projected CRS (UTM 44N / EPSG:32644) so cell units are
      meters — required for meaningful slope + flow math
- [ ] `compute_slope(dem)`, `compute_aspect(dem)`
      → `data/processed/slope.tif`, `aspect.tif`
- [ ] Fill sinks / hydrological conditioning (whitebox `FillDepressions`)
      → `data/processed/dem_filled.tif`  ← the proxy model's key input
- [ ] Flow direction + flow accumulation (whitebox D8)
      → `data/processed/flow_dir.tif`, `flow_acc.tif`

### 1.3 Rainfall module — `src/pipeline/rainfall.py` (1–2 days)
- [ ] `fetch_rainfall(year_range, bbox) -> DataFrame` via imdlib
- [ ] `build_design_storms()` — produce a small set of scenario hyetographs:
      e.g. 50 / 100 / 150 / 250 mm-per-day events (250 ≈ Dec 1 2015 Chennai)
- [ ] Export as `data/processed/scenarios.json` — this file is the contract
      the what-if engine consumes

### 1.4 Pipeline runner (1 day)
- [ ] `src/pipeline/run.py` — one command runs 1.2 + 1.3 end-to-end from raw/
- [ ] Add basic sanity tests (output files exist, value ranges plausible,
      CRS correct)
- [ ] Write `data/README.md` (sources, how to re-download, licenses)

**Exit criteria:** `python -m src.pipeline.run` regenerates all of
`data/processed/` from `data/raw/` on a clean checkout.

---

## Phase 2a — Simplified Hydraulic Proxy  [Track A — ~3–5 days]

**Purpose:** produce believable flood-depth rasters per rainfall scenario,
in the exact output format Track B will later fill with real HEC-RAS results.

### 2a.1 Method (pick one, document choice in devlog)
- [ ] Option 1 (simpler, start here): **fill-and-spill depression flooding** —
      distribute scenario rainfall volume into DEM depressions by elevation
      priority (priority-flood algorithm), giving depth = water surface − ground
- [ ] Option 2 (stretch): coarse cellular-automata / simplified shallow-water
      routing over flow_dir for time-stepped spread
- [ ] Runoff coefficient parameter (urban ~0.7–0.9) to convert rainfall →
      effective surface water; expose as a tunable input

### 2a.2 Implementation — `src/hydraulics/proxy.py`
- [ ] `simulate(scenario, params) -> depth_raster (GeoTIFF)`
      → `data/processed/depth_<scenario>.tif`
- [ ] **Output contract** (write it down in `src/hydraulics/README.md`):
      depth raster, same grid/CRS as clipped DEM, meters, nodata = -9999.
      Track B's HEC-RAS adapter must emit exactly this. This contract is
      what makes the swap a substitution, not a rebuild.
- [ ] Precompute depth rasters for all scenarios in `scenarios.json`
- [ ] Sanity check in QGIS: water should pool in streets/low areas you can
      visually recognize (Velachery lake bed, underpasses)

**Exit criteria:** one depth GeoTIFF per scenario, visually plausible,
format contract documented.

---

## Phase 4 — What-If Simulation Engine  [Track A — ~3–4 days]
*(numbering kept from original roadmap; Phase 3 validation moves to Track B)*

- [ ] Decision: precomputed-scenario interpolation (fast, simple — recommended
      for MVP) vs. on-demand proxy runs (slower, more flexible)
- [ ] `src/simulation/engine.py`: `get_flood_state(rainfall_mm, runoff_coeff)`
      → returns depth grid, interpolating between precomputed scenarios
- [ ] Convert depth rasters → web-friendly format: either downsampled
      PNG tiles + bounds, or JSON grid — benchmark size, target <2–3 MB
      per scenario for smooth frontend loading
- [ ] Expose as tiny local API (FastAPI, 2 endpoints: /scenarios, /flood_state)
      OR fully static precomputed files if interpolation runs client-side
      (simpler deployment — prefer this if feasible)

**Exit criteria:** calling the engine with any rainfall value in range returns
a depth grid in <1s.

---

## Phase 5 — Visualization Frontend  [Track A — ~4–6 days]

- [ ] Stack: React + Vite + **MapLibre GL** (free, no Mapbox token) + deck.gl
      overlay for the depth layer
- [ ] Base map centered on zone, DEM hillshade optional
- [ ] Flood depth layer: colormap shallow→deep (light blue→dark blue),
      opacity slider
- [ ] Controls: rainfall-intensity slider (mapped to engine), runoff/drainage
      parameter slider, scenario preset buttons ("2015-like event")
- [ ] Click a point → show depth at that location
- [ ] Baseline vs. scenario comparison toggle
- [ ] Deploy static build (GitHub Pages / Netlify) if engine is client-side
- [ ] Polish pass: legend, about panel (data sources + proxy disclaimer),
      mobile-usable

**Exit criteria:** a URL you can send someone; they move a slider and see
flooding change on a real Chennai neighborhood.

---

## Phase 3 — Historical Validation  [Track B — needs real hydraulics]
- [ ] After 2b: run Dec 2015 event, compare extent vs. documented flooding
      (news, Sentinel-1 imagery if findable)
- [ ] `VALIDATION.md` with honest accuracy notes
- [ ] (Optional early version: eyeball proxy output vs. known 2015
      waterlogging spots; label clearly as qualitative only)

## Phase 2b — Real HEC-RAS  [Track B — needs Windows]
- [ ] Manual RAS Mapper terrain import → 2D flow area over zone polygon
      → rain-on-grid boundary condition → unsteady run
- [ ] Manning's n layer from OSM land use (roads/buildings/vegetation)
- [ ] RAS-Commander automation of runs per scenario
- [ ] Adapter `src/hydraulics/hecras_adapter.py` emitting the Phase 2a
      output contract → frontend upgrade is automatic
- [ ] Update README: proxy → HEC-RAS upgrade story

## Phase 6 — Expansion & Documentation  [Track A+B]
- [ ] Generalize pipeline config to second city (data availability first)
- [ ] Full README: problem, architecture diagram, methodology, limitations,
      how-to-run, demo GIF
- [ ] Devlog-derived "engineering decisions" writeup — portfolio gold

---

## Sequencing Summary (Track A, from today)
Days 1–2: Phase 0 close-out → Days 3–8: Phase 1 → Days 9–13: Phase 2a →
Days 14–17: Phase 4 → Days 18–23: Phase 5 → buffer/polish.
~3–4 weeks to a live, shareable prototype, no Windows required.



## Phase 7 — Drainage Route Recommendation Engine

**Goal:** Move from "here's where it floods" to "here's what to do about
it" — the literal meaning of the project's name, not yet built.

- [ ] Identify candidate drain/culvert locations using flow accumulation
      data — high-accumulation cells along low-elevation paths are
      natural drainage line candidates
- [ ] Basic culvert sizing calculations (Manning's equation for open
      channel flow, or standard culvert sizing charts) given upstream
      catchment area and design rainfall
- [ ] Simple route optimization: given candidate drain points, suggest
      a connected network to nearest discharge point (could start with
      least-cost path over the flow-direction raster — you already
      have this data from Phase 1)
- [ ] Output: a recommended drainage network layer (GeoJSON lines) with
      per-segment sizing suggestions, viewable on the frontend map
- [ ] Explicit engineering-judgment disclaimer: these are data-driven
      suggestions, not certified engineering designs — same honesty
      pattern as the rest of the project

**Exit criteria:** for the Velachery zone, the app suggests at least
one plausible drainage improvement with a sizing justification a
civil engineer could sanity-check.

---

## Phase 8 — Automated Report Generation

**Goal:** One-click professional output — the "download report" step
their pitch describes, but actually built.

- [ ] Report template: problem summary, zone overview map, scenario
      comparison table, flood statistics (flooded %, max depth, volume),
      drainage recommendations from Phase 7, data sources/methodology
      appendix
- [ ] Implementation: Python-side generation (`reportlab` or
      `weasyprint` from an HTML/Jinja2 template) — produces PDF from
      whichever scenario/parameters the user selected on the frontend
- [ ] Frontend: "Generate Report" button on the dashboard, triggers
      client-side or lightweight serverless generation (keep the
      no-backend architecture if possible — e.g. generate report data
      client-side, render via a PDF library in-browser)
- [ ] Include the honesty/limitations section automatically in every
      report — non-negotiable, keeps every output consistent with the
      project's stated scope

**Exit criteria:** a user can click one button and download a
shareable PDF summarizing a specific flood scenario for the zone.

---

## Phase 9 — Advanced Analysis & Usability

**Goal:** Convenience features that make the tool genuinely nicer to
use, not just technically capable.

- [ ] Multi-scenario side-by-side comparison view (beyond the single
      baseline-vs-scenario toggle from Phase 6's optional polish)
- [ ] Session/project state: let a user save a specific
      rainfall/runoff configuration and return to it later (URL params
      are the simplest version — no backend needed)
- [ ] Export current view as an image/map snapshot (not just the full
      PDF report — quick share-a-screenshot capability)
- [ ] Basic accessibility/UX pass: keyboard navigation for sliders,
      color-blind-safe palette option for the depth colormap
- [ ] Performance check once Phase 7/8 features are added — confirm
      the app is still fast and the static-deployment architecture
      still holds, or make a deliberate call to add a lightweight
      backend if genuinely needed

**Exit criteria:** the tool feels like a polished product, not just a
working prototype — someone unfamiliar with the project could use it
without guidance.

---

## Phase 10 — Multi-City Expansion at Scale

**Goal:** Generalize beyond Velachery/Chennai — this extends what
Phase 6 started, once the pipeline + recommendation engine + reports
are all proven on one city.

- [ ] Config-driven zone definitions (not hardcoded paths) so adding a
      city is a config change, not a code change
- [ ] Add 2-3 more Indian cities with known flood risk and available
      DEM/rainfall data coverage
- [ ] Cross-city comparison view (optional stretch)
- [ ] Document the "adding a new city" process clearly — this is what
      turns the project from "a Chennai tool" into "a platform,"
      matching the original scaling ambition without overclaiming
      before it's true

**Exit criteria:** a second city is live on the deployed site with the
same feature set as Velachery, following a documented, repeatable process.

---

## Sequencing Note

Phases 7-10 are intentionally sequenced **after** Track B (real
HEC-RAS integration, Phase 2b/3) — building recommendation engines
and reports on top of proxy-model data now would mean redoing that
work once real hydraulics replace the proxy. Track A/B completion
first, then 7 → 8 → 9 → 10, each independently shippable and
demoable on its own.