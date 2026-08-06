// Loads web_meta.json + the per-scenario binary depth grids and answers
// what-if queries, mirroring src/simulation/engine.py exactly.
//
// Binary format (src/simulation/README.md): headerless uint16 little-endian,
// depth in millimeters, nodata 65535, row-major, row 0 = north edge.

export const NODATA = 65535;

export async function loadFloodData(baseUrl = "data/") {
  const meta = await (await fetch(`${baseUrl}web_meta.json`)).json();
  const scenarios = [...meta.scenarios].sort((a, b) => a.rainfall_mm - b.rainfall_mm);

  const grids = await Promise.all(
    scenarios.map(async (s) => {
      const buf = await (await fetch(`${baseUrl}${s.file}`)).arrayBuffer();
      const grid = new Uint16Array(buf); // browsers are little-endian, matching the file
      if (grid.length !== meta.width * meta.height) {
        throw new Error(`${s.file}: ${grid.length} cells, expected ${meta.width * meta.height}`);
      }
      return grid;
    })
  );

  // Anchor list mirrors the engine: synthetic all-dry grid at 0 mm, then the
  // precomputed scenarios in rainfall order. The nodata mask is shared, so the
  // zero anchor copies it from the first real grid.
  const zero = new Uint16Array(grids[0].length);
  for (let i = 0; i < zero.length; i++) if (grids[0][i] === NODATA) zero[i] = NODATA;

  return {
    meta,
    anchors: [
      { rainfall_mm: 0, grid: zero },
      ...scenarios.map((s, i) => ({ ...s, grid: grids[i] })),
    ],
    maxRainfall: scenarios[scenarios.length - 1].rainfall_mm,
  };
}

// Per-cell linear interpolation between the two anchors bracketing the
// equivalent rainfall. Returns Float32Array of depth in METERS (NaN = nodata).
//
// Runoff coefficient folds into equivalent rainfall (mm * coeff / 0.75) — the
// volume-folding identity: the proxy's output depends only on effective
// volume, so this is exact for proxy data. It will NOT hold for Track B
// HEC-RAS output (time-dynamic); revisit then.
export function floodGrid(data, rainfallMm, runoffCoeff) {
  const { anchors, meta } = data;
  const eq = (rainfallMm * runoffCoeff) / meta.base_runoff_coeff;
  const top = anchors[anchors.length - 1];

  let lo = anchors[0];
  let hi = top;
  let t = 1;
  if (eq >= top.rainfall_mm) {
    lo = top; // clamped: never extrapolate past depression capacity
  } else {
    for (let i = 1; i < anchors.length; i++) {
      if (anchors[i].rainfall_mm >= eq) {
        lo = anchors[i - 1];
        hi = anchors[i];
        t = (eq - lo.rainfall_mm) / (hi.rainfall_mm - lo.rainfall_mm);
        break;
      }
    }
  }

  const out = new Float32Array(lo.grid.length);
  for (let i = 0; i < out.length; i++) {
    const a = lo.grid[i];
    if (a === NODATA) {
      out[i] = NaN;
    } else if (lo === hi) {
      out[i] = a / 1000;
    } else {
      out[i] = ((1 - t) * a + t * hi.grid[i]) / 1000;
    }
  }
  return out;
}

// True when the query is past the top anchor (shown in the UI so clamping
// is visible rather than silent).
export function isClamped(data, rainfallMm, runoffCoeff) {
  return (rainfallMm * runoffCoeff) / data.meta.base_runoff_coeff > data.maxRainfall;
}

// Depth (meters) at a lon/lat for a computed grid; null outside data area.
export function depthAt(data, grid, lon, lat) {
  const { bounds, width, height } = data.meta;
  const col = Math.floor(((lon - bounds.west) / (bounds.east - bounds.west)) * width);
  const row = Math.floor(((bounds.north - lat) / (bounds.north - bounds.south)) * height);
  if (col < 0 || col >= width || row < 0 || row >= height) return null;
  const d = grid[row * width + col];
  return Number.isNaN(d) ? null : d;
}
