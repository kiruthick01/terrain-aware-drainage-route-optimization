// Rainfall + runoff sliders and scenario presets. The runoff slider works via
// the volume-folding identity (rain x coeff / 0.75 = equivalent rainfall) —
// exact for proxy data; revisit when Track B (HEC-RAS) replaces it.

const PRESETS = [
  { label: "Heavy day (50mm)", rainfall: 50 },
  { label: "Very heavy (100mm)", rainfall: 100 },
  { label: "Nov 2015-class (250mm)", rainfall: 250 },
  { label: "2015 flood peak (350mm)", rainfall: 350 },
];

export default function Controls({ data, rainfall, runoff, clamped, onRainfall, onRunoff }) {
  return (
    <div className="panel controls">
      <h1>Chennai Flood What-If</h1>
      <p className="subtitle">Velachery zone — proxy hydraulics</p>

      <label>
        Rainfall: <strong>{rainfall} mm/day</strong>
        <input
          type="range"
          min="0"
          max="500"
          step="5"
          value={rainfall}
          onChange={(e) => onRainfall(Number(e.target.value))}
        />
      </label>

      <label>
        Runoff coefficient: <strong>{runoff.toFixed(2)}</strong>
        <input
          type="range"
          min="0.1"
          max="1"
          step="0.05"
          value={runoff}
          onChange={(e) => onRunoff(Number(e.target.value))}
        />
        <span className="hint">0.1 ≈ vegetated, 0.9 ≈ dense concrete</span>
      </label>

      {clamped && (
        <p className="clamp-warning">
          Beyond the {data.maxRainfall} mm scenario — depths clamped at maximum
          (depressions full; no extrapolation past terrain capacity).
        </p>
      )}

      <div className="presets">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            className={rainfall === p.rainfall ? "active" : ""}
            onClick={() => onRainfall(p.rainfall)}
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}
