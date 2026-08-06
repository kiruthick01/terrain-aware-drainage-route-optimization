# Simulation engine + web export format

## Engine (`engine.py`)

`get_flood_state(rainfall_mm, runoff_coeff=0.75) -> np.ndarray`

- Returns float32 depth grid (meters), same grid/CRS as
  `dem_reprojected.tif`, nodata −9999. Answers in ~1 ms after first call
  (rasters cached on first query).
- Linear per-cell interpolation between the two precomputed scenario rasters
  bracketing the query, plus a physical zero anchor (0 mm → dry everywhere).
- Runoff coefficient folds into an equivalent rainfall
  (`rainfall x coeff / 0.75`) — **exact** for the fill-and-spill proxy, whose
  output depends only on effective volume. Track B's HEC-RAS results are
  time-dynamic and will not obey this identity; real hydraulics needs
  per-coefficient precomputed runs.
- Queries above the top scenario (350 mm equivalent) are clamped, not
  extrapolated — the top scenario already fills ~96% of total depression
  capacity, so extrapolation would invent water the terrain cannot hold.

## Web export format (`export.py` → `data/processed/web/`)

One binary grid per scenario + one shared metadata file. Everything the
frontend needs; no server, no GeoTIFF parsing in the browser.

### `web_meta.json`

```json
{
  "version": 1,
  "crs": "EPSG:4326",
  "width": 251, "height": 188,
  "bounds": {"west": ..., "south": ..., "east": ..., "north": ...},
  "units": "mm", "dtype": "uint16", "endianness": "little",
  "order": "row-major, row 0 = northernmost",
  "nodata": 65535,
  "base_runoff_coeff": 0.75,
  "scenarios": [
    {"name": "moderate", "rainfall_mm": 50, "file": "depth_moderate.bin",
     "max_depth_mm": 5932}
  ]
}
```

(`width`/`height`/`bounds` above are illustrative — always read them from the
file, never hardcode.)

### `depth_<name>.bin` — byte layout

| Property   | Value                                                      |
|------------|------------------------------------------------------------|
| Content    | `width x height` uint16 values, no header, no padding      |
| Size       | exactly `width * height * 2` bytes                         |
| Byte order | little-endian                                              |
| Value      | standing-water depth in **millimeters** (0 = dry)          |
| Nodata     | 65535 (outside valid DEM area)                             |
| Layout     | row-major; index `row * width + col`; row 0 = north edge, col 0 = west edge |
| Georef     | cell (row, col) center: lon = west + (col + 0.5) * (east - west) / width, lat = north - (row + 0.5) * (north - south) / height |

Grid is north-up in EPSG:4326 — drapes directly onto a web map using
`bounds`, no reprojection needed client-side.

### Decoding in JS

```js
const meta = await (await fetch("web_meta.json")).json();
const buf = await (await fetch(meta.scenarios[0].file)).arrayBuffer();
const grid = new Uint16Array(buf);          // platform-LE, see note
const depthM = (row, col) => {
  const v = grid[row * meta.width + col];
  return v === meta.nodata ? null : v / 1000;   // mm -> meters
};
```

Note: `Uint16Array` assumes platform endianness; every mainstream browser
platform is little-endian, matching the file. For belt-and-braces decoding
use `new DataView(buf).getUint16(i * 2, /* littleEndian */ true)`.

### Client-side what-if (mirrors the engine)

```js
function floodGrid(rainfallMm, runoffCoeff, meta, grids /* name -> Uint16Array */) {
  const eq = rainfallMm * runoffCoeff / meta.base_runoff_coeff;
  const anchors = [{rainfall_mm: 0, grid: null /* all zeros */},
                   ...meta.scenarios];          // already sorted by rainfall
  // find bracket [lo, hi] around eq, clamp at top, then per cell:
  // depth = (1 - t) * lo[i] + t * hi[i]   (nodata if either is 65535)
}
```

Total payload: 5 grids ≈ 460 KB raw (see export log for exact numbers);
serve gzipped and it compresses further — zeros dominate.
