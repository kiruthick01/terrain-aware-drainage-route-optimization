# Project Roadmap — terrain-aware-drainage-route-optimization

> Scope: Interactive flood-risk analysis and "what-if" scenario simulation for
> select flood-prone zones in Chennai (and later, other Indian cities).
> Goal: A technically strong, fully self-built, portfolio-grade project —
> not a rushed demo.

---

## Guiding Principles
- Build slow, build real. No shortcuts on validation or documentation.
- Every phase should end in something demoable, even if small.
- Commit daily, even if it's a small step — momentum > speed.
- Keep a `NOTES.md` or `devlog/` folder logging decisions and why you made them.

---

## Phase 0 — Foundations & Scoping
**Goal:** Clear scope, working environment, project skeleton.

- [ ] Pick 1–2 known waterlogging zones in Chennai to start (e.g. Velachery, Mudichur, Adyar basin)
- [ ] Research available public data sources:
  - [ ] Bhuvan (ISRO) DEM data
  - [ ] SRTM / Copernicus DEM (global fallback)
  - [ ] OpenStreetMap drainage/water layers for the zone
  - [ ] IMD historical rainfall data
- [ ] Set up GitHub repo (private until ready), README with problem statement
- [ ] Set up Python environment (conda/venv), core libs: `rasterio`, `gdal`, `geopandas`, `numpy`
- [ ] Create `devlog/` folder for daily notes

**Suggested daily breakdown (approx. 1 week):**
- Day 1: Repo setup, environment setup, README draft
- Day 2: Research + shortlist target zone(s) and data sources
- Day 3: Download and inspect sample DEM data for the zone
- Day 4: Write project scope doc — what MVP success looks like
- Day 5: Buffer / catch-up + write first devlog entry

---

## Phase 1 — Data Pipeline
**Goal:** Clean, reusable terrain data pipeline for your chosen zone.

- [ ] Script to download/clip DEM to zone boundary
- [ ] Compute elevation, slope, aspect rasters
- [ ] Visualize terrain data (matplotlib / QGIS) to sanity-check
- [ ] Package pipeline as reusable Python module (not just notebook scripts)

**Suggested daily breakdown (approx. 1–2 weeks):**
- Day 1–2: DEM download + clipping script
- Day 3–4: Slope/aspect/elevation feature extraction
- Day 5: Visualization + sanity checks
- Day 6–7: Refactor into clean reusable module + write tests

---

## Phase 2 — HEC-RAS Hydraulic Modeling
**Goal:** Understand HEC-RAS deeply, then automate it.

- [ ] Manually build a HEC-RAS 2D model for your chosen zone (GUI first)
- [ ] Document the manual workflow step by step (for your own reference)
- [ ] Explore RAS-Commander (Python API for HEC-RAS automation)
- [ ] Script model setup + execution via RAS-Commander
- [ ] Extract results: water surface elevation (WSE), depth, velocity rasters

**This will likely be your longest phase — don't rush it.**

---

## Phase 3 — Flood-Risk & Historical Validation
**Goal:** Ground the model in real-world flood history.

- [ ] Integrate historical rainfall data (IMD or open APIs)
- [ ] Run model against a known past flood event in your zone
- [ ] Compare model output vs. known flood extent (news reports, satellite imagery)
- [ ] Document accuracy/limitations honestly in `VALIDATION.md`

---

## Phase 4 — What-If Simulation Engine (Core Differentiator)
**Goal:** Real-time-ish interactive scenario modeling, not just static reports.

- [ ] Prototype a lightweight shallow-water / surrogate model on toy data first
- [ ] Explore GPU-based approaches (WebGL/shader-based, à la WebFlood) OR
      a surrogate ML model trained on your HEC-RAS outputs for speed
- [ ] Build ability to tweak inputs (rainfall intensity, drainage capacity)
      and get near-real-time updated flood extent
- [ ] Benchmark speed vs. accuracy trade-off vs. full HEC-RAS re-run

**Prototype the toy version before wiring it to real HEC-RAS outputs.**

---

## Phase 5 — Visualization Frontend
**Goal:** A polished, interactive map-based dashboard.

- [ ] Choose stack: deck.gl / Mapbox GL / Leaflet
- [ ] Render flood extent, depth, and risk zones on map
- [ ] Add sliders/controls for what-if scenario inputs
- [ ] Add comparison view (baseline vs. scenario)
- [ ] Polish UI/UX — this is what people will actually see

---

## Phase 6 — Expansion & Documentation
**Goal:** Generalize, document, and package for portfolio use.

- [ ] Generalize pipeline to 1–2 more Indian cities
- [ ] Write full technical README + methodology write-up
- [ ] Write "how this differs from existing approaches" section
- [ ] Record a demo video/GIF for GitHub
- [ ] Final polish pass on code quality, tests, docs

---

## Tech Stack (tentative)
- **Data/GIS:** Python, rasterio, GDAL, geopandas, whitebox-tools
- **Hydraulics:** HEC-RAS 2D + RAS-Commander (Python API)
- **Simulation layer:** WebGL/shader-based or ML surrogate model
- **Frontend:** deck.gl / Mapbox GL / Leaflet + React (or similar)
- **Infra:** GitHub, devlog-based tracking, README-driven documentation

---

## Notes
- This is not affiliated with, nor uses code/credit from, any existing team project.
- Naming: terrain-aware-drainage-route-optimization