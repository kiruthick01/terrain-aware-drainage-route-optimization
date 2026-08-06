import { useState } from "react";

export default function InfoPanel({ clicked }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="panel info">
      {clicked && (
        <div className="click-readout">
          {clicked.depth === null ? (
            <span>Outside data area</span>
          ) : clicked.depth < 0.05 ? (
            <span>Dry at clicked point</span>
          ) : (
            <span>
              Depth <strong>{clicked.depth.toFixed(2)} m</strong> at{" "}
              {clicked.lat.toFixed(4)}°N, {clicked.lon.toFixed(4)}°E
            </span>
          )}
        </div>
      )}
      <button className="about-toggle" onClick={() => setOpen(!open)}>
        {open ? "Hide info" : "About this map"}
      </button>
      {open && (
        <div className="about">
          <p>
            Interactive flood-risk what-if for Velachery, Chennai. Pick a
            rainfall scenario; the map shows where water pools and how deep.
          </p>
          <p>
            <strong>Honesty note:</strong> depths come from a simplified
            fill-and-spill terrain model (depression flooding by elevation
            priority), <em>not</em> a hydraulic solver. No overland routing,
            no time dynamics, no storm drains. Indicative — "where pools
            first, roughly how deep" — not engineering-grade. A HEC-RAS 2D
            upgrade is planned via the same data contract.
          </p>
          <p>
            Data: SRTM GL1 30m DEM (OpenTopography, NASA/USGS), IMD 0.25°
            gridded daily rainfall (2015 anchors). Scenario magnitudes match
            the observed 2015 record — the 350mm preset is the Dec 1–2 2015
            flood peak at the nearest IMD land cell.
          </p>
        </div>
      )}
    </div>
  );
}
