import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { BitmapLayer } from "@deck.gl/layers";
import "maplibre-gl/dist/maplibre-gl.css";
import { loadFloodData, floodGrid, depthAt, isClamped } from "./lib/floodData";
import { gridToCanvas } from "./lib/colormap";
import Controls from "./components/Controls";
import Legend from "./components/Legend";
import InfoPanel from "./components/InfoPanel";
import "./App.css";

// Free raster basemap, no token; attribution required and shown.
const BASEMAP_STYLE = {
  version: 8,
  sources: {
    carto: {
      type: "raster",
      tiles: ["https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png"],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
    },
  },
  layers: [{ id: "carto", type: "raster", source: "carto" }],
};

export default function App() {
  const mapContainer = useRef(null);
  const mapRef = useRef(null);
  const overlayRef = useRef(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [rainfall, setRainfall] = useState(100);
  const [runoff, setRunoff] = useState(0.75);
  const [clicked, setClicked] = useState(null); // {lon, lat, depth}

  // Current interpolated grid — recomputed only when inputs change.
  const grid = useMemo(
    () => (data ? floodGrid(data, rainfall, runoff) : null),
    [data, rainfall, runoff]
  );

  useEffect(() => {
    loadFloodData().then(setData).catch((e) => setError(String(e)));
  }, []);

  // Map + overlay created once, after data arrives (bounds come from meta).
  useEffect(() => {
    if (!data || mapRef.current) return;
    const { bounds } = data.meta;
    const map = new maplibregl.Map({
      container: mapContainer.current,
      style: BASEMAP_STYLE,
      bounds: [bounds.west, bounds.south, bounds.east, bounds.north],
      fitBoundsOptions: { padding: 40 },
    });
    const overlay = new MapboxOverlay({ layers: [] });
    map.addControl(overlay);
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current = map;
    overlayRef.current = overlay;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [data]);

  // New immutable BitmapLayer per grid change; deck diffs and re-uploads
  // only the image. pickable: false — clicks handled via MapLibre below.
  useEffect(() => {
    if (!data || !grid || !overlayRef.current) return;
    const { bounds, width, height } = data.meta;
    overlayRef.current.setProps({
      layers: [
        new BitmapLayer({
          id: "flood-depth",
          image: gridToCanvas(grid, width, height),
          bounds: [bounds.west, bounds.south, bounds.east, bounds.north],
          pickable: false,
        }),
      ],
    });
  }, [data, grid]);

  // Click-to-query: lon/lat -> row/col -> depth for the CURRENT grid.
  useEffect(() => {
    if (!mapRef.current || !data || !grid) return;
    const handler = (e) => {
      const depth = depthAt(data, grid, e.lngLat.lng, e.lngLat.lat);
      setClicked({ lon: e.lngLat.lng, lat: e.lngLat.lat, depth });
    };
    const map = mapRef.current;
    map.on("click", handler);
    return () => map.off("click", handler);
  }, [data, grid]);

  if (error) return <div className="error">Failed to load flood data: {error}</div>;

  return (
    <div className="app">
      <div ref={mapContainer} className="map" />
      {data && (
        <>
          <Controls
            data={data}
            rainfall={rainfall}
            runoff={runoff}
            clamped={isClamped(data, rainfall, runoff)}
            onRainfall={setRainfall}
            onRunoff={setRunoff}
          />
          <Legend />
          <InfoPanel clicked={clicked} />
        </>
      )}
      {!data && !error && <div className="loading">Loading flood data…</div>}
    </div>
  );
}
