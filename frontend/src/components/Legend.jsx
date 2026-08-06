import { DEPTH_STOPS } from "../lib/colormap";

export default function Legend() {
  const gradient = `linear-gradient(to right, ${DEPTH_STOPS.map(
    (s) => `rgb(${s.color.join(",")})`
  ).join(", ")})`;

  return (
    <div className="panel legend">
      <div className="legend-title">Water depth (m)</div>
      <div className="legend-bar" style={{ background: gradient }} />
      <div className="legend-labels">
        {DEPTH_STOPS.map((s) => (
          <span key={s.label}>{s.label}</span>
        ))}
      </div>
    </div>
  );
}
