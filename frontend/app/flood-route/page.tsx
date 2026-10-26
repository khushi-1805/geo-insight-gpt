"use client";

import { useState } from "react";
import dynamic from "next/dynamic";

const FloodRouteMap = dynamic(
  () => import("./FloodRouteMap"),
  { ssr: false }
);
export default function FloodRoutePage() {
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [loading, setLoading] = useState(false);
const [result, setResult] = useState<any>(null);

const findSafestRoute = async () => {
  if (!origin || !destination) {
    alert("Please enter both locations.");
    return;
  }

  try {
    setLoading(true);

    const response = await fetch(
      `http://127.0.0.1:8000/flood/analyze?origin=${encodeURIComponent(
        origin
      )}&destination=${encodeURIComponent(destination)}`
    );

    if (!response.ok) {
      throw new Error("Flood analysis failed");
    }

    const data = await response.json();

    setResult(data);
  } catch (error) {
    console.error(error);
    alert("Could not analyze the route.");
  } finally {
    setLoading(false);
  }
};
  return (
    <main className="min-h-screen bg-[#0b1020] text-white">
      {/* Header */}
      <header className="border-b border-white/10 px-8 py-5">
        <h1 className="text-2xl font-semibold">
          🌊 Flood-Safe Route Planner
        </h1>

        <p className="mt-1 text-sm text-slate-400">
          Find the safest route based on flood conditions.
        </p>
      </header>

      {/* Main content */}
      <div className="p-8">
        <div className="max-w-6xl space-y-5">
          
          {/* Origin */}
          <div>
            <label className="mb-2 block text-sm text-slate-300">
              From
            </label>

            <input
              type="text"
              value={origin}
              onChange={(e) => setOrigin(e.target.value)}
              placeholder="Enter starting location"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white outline-none placeholder:text-slate-500 focus:border-blue-500"
            />
          </div>

          {/* Destination */}
          <div>
            <label className="mb-2 block text-sm text-slate-300">
              To
            </label>

            <input
              type="text"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="Enter destination"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white outline-none placeholder:text-slate-500 focus:border-blue-500"
            />
          </div>

          {/* Button */}
          <button
  onClick={findSafestRoute}
  disabled={loading}
  className="w-full rounded-lg bg-blue-600 px-4 py-3 font-medium transition hover:bg-blue-500 disabled:opacity-50"
>
  {loading ? "Analyzing..." : "Find Safest Route"}
</button>
{result && (
  <div className="mt-8 space-y-6">
    {/* Map */}
    <div className="h-[550px] w-full overflow-hidden rounded-2xl border border-white/10">
      <FloodRouteMap
        origin={result.origin}
        destination={result.destination}
        routes={result.routes}
        safestRouteId={result.safest_route.route_id}
      />
    </div>

    {/* Recommended route */}
    <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
      <h2 className="text-xl font-semibold">
        🛡 Recommended Route
      </h2>

      <div className="mt-4 space-y-2 text-sm text-slate-300">
        <p>
          Risk:{" "}
          <span className="font-semibold text-green-400">
            {result.safest_route.flood_risk.risk.toUpperCase()}
          </span>
        </p>

        <p>
          Flood exposure:{" "}
          {result.safest_route.flood_risk.flooded_percentage}%
        </p>

        <p>
          Distance:{" "}
          {(result.safest_route.flood_risk.route_length_m / 1000).toFixed(2)} km
        </p>
      </div>
    </div>
  </div>
)}
        </div>
      </div>
    </main>
  );
}