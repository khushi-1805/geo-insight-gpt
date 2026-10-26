"use client";

import {
  MapContainer,
  TileLayer,
  Polyline,
  Marker,
  Popup,
  useMap,
} from "react-leaflet";
import { useEffect } from "react";

type Route = {
  route_id: number;
  path: [number, number][];
  flood_risk?: {
    flooded_percentage?: number;
    risk?: string;
  };
};

type FloodRouteMapProps = {
  origin: {
    latitude: number;
    longitude: number;
    title?: string;
  };
  destination: {
    latitude: number;
    longitude: number;
    title?: string;
  };
  routes: Route[];
  safestRouteId: number;
};

function FitMap({
  origin,
  destination,
  routes,
}: {
  origin: [number, number];
  destination: [number, number];
  routes: Route[];
}) {
  const map = useMap();

  useEffect(() => {
    const points: [number, number][] = [
      origin,
      destination,
      ...routes.flatMap((route) =>
        route.path.map(([lng, lat]) => [lat, lng] as [number, number])
      ),
    ];

    if (points.length > 0) {
      map.fitBounds(points, {
        padding: [40, 40],
      });
    }
  }, [map, origin, destination, routes]);

  return null;
}

export default function FloodRouteMap({
  origin,
  destination,
  routes,
  safestRouteId,
}: FloodRouteMapProps) {
  const originPosition: [number, number] = [
    origin.latitude,
    origin.longitude,
  ];

  const destinationPosition: [number, number] = [
    destination.latitude,
    destination.longitude,
  ];

  return (
    <MapContainer
      center={originPosition}
      zoom={10}
      style={{
        height: "100%",
        width: "100%",
        borderRadius: "16px",
      }}
    >
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <FitMap
        origin={originPosition}
        destination={destinationPosition}
        routes={routes}
      />

      {/* Origin */}
      <Marker position={originPosition}>
        <Popup>
          <strong>Origin</strong>
          <br />
          {origin.title || "Starting point"}
        </Popup>
      </Marker>

      {/* Destination */}
      <Marker position={destinationPosition}>
        <Popup>
          <strong>Destination</strong>
          <br />
          {destination.title || "Destination"}
        </Popup>
      </Marker>

      {/* Routes */}
      {routes.map((route) => {
        const isSafest = route.route_id === safestRouteId;

        const positions: [number, number][] = route.path.map(
          ([lng, lat]) => [lat, lng]
        );

        return (
          <Polyline
            key={route.route_id}
            positions={positions}
            pathOptions={{
              color: isSafest ? "#2563eb" : route.route_id === 1 ? "#f59e0b" : "#eab308",
              weight: isSafest ? 7 : 4,
              opacity: isSafest ? 1 : 0.7,
            }}
          >
            <Popup>
              <strong>
                <strong>
  {isSafest
    ? "🔵 Recommended Route"
    : `Route ${route.route_id + 1}`}
</strong>
              </strong>
              <br />
              Risk: {route.flood_risk?.risk || "unknown"}
              <br />
              Flood exposure:{" "}
              {route.flood_risk?.flooded_percentage ?? 0}%
            </Popup>
          </Polyline>
        );
      })}
    </MapContainer>
  );
}