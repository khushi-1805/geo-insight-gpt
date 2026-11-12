
"use client";

import { Fragment, useEffect, useMemo } from "react";
import {
  GeoJSON,
  MapContainer,
  Marker,
  Popup,
  Polyline,
  TileLayer,
  useMap,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";
import { divIcon } from "leaflet";

type LatLon = {
  latitude: number;
  longitude: number;
};

type Candidate = LatLon & {
  distance_from_user_m?: number;
  safety_offset_m?: number;
  verification_status?: string;
  warnings?: string[];
};

type Geometry = {
  type: string;
  coordinates: unknown;
};

type FloodEscapeMapProps = {
  userLocation: LatLon;
  waterExtent: Geometry | null;
  floodBoundary: Geometry | null;
  candidates: Candidate[];
};

function collectCoordinates(
  value: unknown,
  output: [number, number][]
) {
  if (!Array.isArray(value)) return;

  if (
    value.length >= 2 &&
    typeof value[0] === "number" &&
    typeof value[1] === "number"
  ) {
    output.push([value[1], value[0]]);
    return;
  }

  value.forEach((item) =>
    collectCoordinates(item, output)
  );
}

function FitEscapeBounds({
  userLocation,
  waterExtent,
  candidates,
}: FloodEscapeMapProps) {
  const map = useMap();

  const bounds = useMemo(() => {
    const points: [number, number][] = [
      [userLocation.latitude, userLocation.longitude],
      ...candidates.map(
        (candidate) =>
          [
            candidate.latitude,
            candidate.longitude,
          ] as [number, number]
      ),
    ];

    if (waterExtent) {
      collectCoordinates(
        waterExtent.coordinates,
        points
      );
    }

    return points;
  }, [userLocation, waterExtent, candidates]);

  useEffect(() => {
    if (bounds.length > 0) {
      map.fitBounds(bounds, {
        padding: [35, 35],
        maxZoom: 15,
      });
    }
  }, [map, bounds]);

  return null;
}

// Blue marker: submitted location
const userIcon = divIcon({
  className: "",
  html: `
    <div style="
      width:22px;
      height:22px;
      background:#2563eb;
      border:3px solid white;
      border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);
      box-shadow:0 2px 8px rgba(0,0,0,.5);
    "></div>
  `,
  iconSize: [22, 22],
  iconAnchor: [11, 22],
});

// Green marker: candidate evacuation point
const candidateIcon = divIcon({
  className: "",
  html: `
    <div style="
      width:18px;
      height:18px;
      background:#16a34a;
      border:3px solid white;
      border-radius:50%;
      box-shadow:0 2px 8px rgba(0,0,0,.5);
    "></div>
  `,
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

export default function FloodEscapeMap({
  userLocation,
  waterExtent,
  floodBoundary,
  candidates,
}: FloodEscapeMapProps) {
  const center: [number, number] = [
    userLocation.latitude,
    userLocation.longitude,
  ];

  const waterFeature = waterExtent
    ? ({
        type: "Feature",
        properties: {},
        geometry: waterExtent,
      } as never)
    : null;

  const boundaryFeature = floodBoundary
    ? ({
        type: "Feature",
        properties: {},
        geometry: floodBoundary,
      } as never)
    : null;

  return (
    <div className="h-[560px] w-full overflow-hidden rounded-2xl border border-white/10">
      <MapContainer
        center={center}
        zoom={12}
        scrollWheelZoom
        style={{
          height: "100%",
          width: "100%",
          background: "#0b1120",
        }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

<FitEscapeBounds
  userLocation={userLocation}
  waterExtent={waterExtent}
  floodBoundary={floodBoundary}
  candidates={candidates}
/>

        {waterFeature && (
          <GeoJSON
            data={waterFeature}
            style={{
              color: "#0284c7",
              weight: 1.5,
              fillColor: "#38bdf8",
              fillOpacity: 0.38,
            }}
          />
        )}

        {boundaryFeature && (
          <GeoJSON
            data={boundaryFeature}
            style={{
              color: "#f97316",
              weight: 3,
              fillOpacity: 0,
            }}
          />
        )}

        {/* Submitted coordinates */}
        <Marker position={center} icon={userIcon}>
          <Popup>
            <strong>Submitted location</strong>
            <br />
            Latitude: {userLocation.latitude.toFixed(6)}
            <br />
            Longitude: {userLocation.longitude.toFixed(6)}
          </Popup>
        </Marker>

        {/* Candidate evacuation points */}
        {candidates.map((candidate, index) => {
          const position: [number, number] = [
            candidate.latitude,
            candidate.longitude,
          ];

          return (
            <Fragment key={`candidate-${index}`}>
              <Polyline
                positions={[center, position]}
                pathOptions={{
                  color: "#eab308",
                  weight: 2,
                  opacity: 0.75,
                  dashArray: "6 7",
                }}
              />

              <Marker
                position={position}
                icon={candidateIcon}
              >
                <Popup>
                  <strong>
                    Candidate exit point {index + 1}
                  </strong>
                  <br />
                  Distance:{" "}
                  {candidate.distance_from_user_m?.toFixed(0) ?? "—"} m
                  <br />
                  Offset: {candidate.safety_offset_m ?? "—"} m
                  <br />
                  Status:{" "}
                  {candidate.verification_status ?? "Unverified"}
                </Popup>
              </Marker>
            </Fragment>
          );
        })}
      </MapContainer>
    </div>
  );
}
