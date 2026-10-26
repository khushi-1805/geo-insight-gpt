"use client";

import { GeoJSON, ImageOverlay, MapContainer, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";

type OverlayBounds = [[number, number], [number, number]];

type BoundaryFeature = {
  type: string;
  properties?: Record<string, unknown>;
  geometry?: {
    type: string;
    coordinates: unknown;
  };
};

type AnalysisMapProps = {
  boundary?: BoundaryFeature | null;
  overlayUrl?: string | null;
  overlayBounds?: OverlayBounds | null;
  center?: {
    latitude: number;
    longitude: number;
  };
};

function featureBounds(boundary?: BoundaryFeature | null): OverlayBounds | null {
  const coordinates = boundary?.geometry?.coordinates;

  if (!coordinates) {
    return null;
  }

  const points: number[][] = [];

  const walk = (value: unknown) => {
    if (!Array.isArray(value)) {
      return;
    }

    if (
      value.length >= 2 &&
      typeof value[0] === "number" &&
      typeof value[1] === "number"
    ) {
      points.push([value[0], value[1]]);
      return;
    }

    value.forEach(walk);
  };

  walk(coordinates);

  if (points.length === 0) {
    return null;
  }

  const lngs = points.map((point) => point[0]);
  const lats = points.map((point) => point[1]);

  return [
    [Math.min(...lats), Math.min(...lngs)],
    [Math.max(...lats), Math.max(...lngs)],
  ];
}

export default function AnalysisMap({
  boundary,
  overlayUrl,
  overlayBounds,
  center,
}: AnalysisMapProps) {
  const bounds =
    overlayBounds ||
    featureBounds(boundary) ||
    (center
      ? [
          [center.latitude - 0.15, center.longitude - 0.15],
          [center.latitude + 0.15, center.longitude + 0.15],
        ]
      : null);

  if (!bounds) {
    return null;
  }

  const resolvedOverlay =
    overlayUrl && overlayUrl.startsWith("http")
      ? overlayUrl
      : overlayUrl
        ? `http://127.0.0.1:8000${overlayUrl}`
        : null;

  return (
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025]">
      <div className="border-b border-white/10 px-5 py-4">
        <h3 className="text-sm font-semibold">Analysis region</h3>
        <p className="mt-1 text-xs text-white/35">
          Boundary from the location resolver
          {resolvedOverlay ? " with a colored index overlay" : ""}
        </p>
      </div>

      <div className="h-80 w-full">
        <MapContainer
          bounds={bounds}
          className="h-full w-full"
          scrollWheelZoom
          style={{ height: "100%", width: "100%", background: "#0b1120" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {boundary?.geometry ? (
            <GeoJSON
              data={boundary as never}
              style={{
                color: "#22d3ee",
                weight: 2,
                fillColor: "#22d3ee",
                fillOpacity: 0.08,
              }}
            />
          ) : null}

          {resolvedOverlay && overlayBounds ? (
            <ImageOverlay
              bounds={overlayBounds}
              opacity={0.65}
              url={resolvedOverlay}
            />
          ) : null}
        </MapContainer>
      </div>
    </div>
  );
}
