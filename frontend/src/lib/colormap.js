// Sequential single-hue colormap for flood depth (magnitude data: one hue,
// light -> dark). Depth distribution is heavily skewed (most wet cells
// < 1 m, max ~7.4 m), so stops are spaced non-linearly to spend color
// resolution where the data lives.

export const DEPTH_STOPS = [
  { depth: 0.05, color: [219, 234, 254], label: "0.05" }, // barely wet
  { depth: 0.25, color: [147, 197, 253], label: "0.25" },
  { depth: 0.5, color: [96, 165, 250], label: "0.5" },
  { depth: 1.0, color: [59, 130, 246], label: "1" },
  { depth: 2.0, color: [37, 99, 235], label: "2" },
  { depth: 4.0, color: [29, 78, 216], label: "4" },
  { depth: 7.5, color: [23, 37, 84], label: "7+" }, // deepest depressions
];

const OPACITY = 0.8; // basemap must stay readable underneath

// Depth (m) -> [r, g, b, a]; transparent when dry (< first stop) or nodata.
export function depthToColor(depth) {
  if (Number.isNaN(depth) || depth < DEPTH_STOPS[0].depth) return [0, 0, 0, 0];
  const last = DEPTH_STOPS[DEPTH_STOPS.length - 1];
  if (depth >= last.depth) return [...last.color, Math.round(OPACITY * 255)];

  let i = 1;
  while (DEPTH_STOPS[i].depth < depth) i++;
  const a = DEPTH_STOPS[i - 1];
  const b = DEPTH_STOPS[i];
  const t = (depth - a.depth) / (b.depth - a.depth);
  return [
    Math.round(a.color[0] + t * (b.color[0] - a.color[0])),
    Math.round(a.color[1] + t * (b.color[1] - a.color[1])),
    Math.round(a.color[2] + t * (b.color[2] - a.color[2])),
    Math.round(OPACITY * 255),
  ];
}

// Render a depth grid to an offscreen canvas for deck.gl's BitmapLayer.
// 251x188 cells -> regenerating on every slider tick is trivially cheap.
export function gridToCanvas(grid, width, height) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(width, height);
  for (let i = 0; i < grid.length; i++) {
    const [r, g, b, a] = depthToColor(grid[i]);
    img.data[i * 4] = r;
    img.data[i * 4 + 1] = g;
    img.data[i * 4 + 2] = b;
    img.data[i * 4 + 3] = a;
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}
