 "use client";

import { useState } from "react";
import dynamic from "next/dynamic";

const FloodEscapeMap = dynamic(
  () =>
    import("./FloodEscapeMap").then(
      (module) => module.default
    ),
  {
    ssr: false,
    loading: () => (
      <div className="h-[560px] flex items-center justify-center text-slate-400">
        Loading evacuation map...
      </div>
    ),
  }
);

type EscapeCandidate = {
  latitude: number;
  longitude: number;
  distance_from_user_m?: number;
  safety_offset_m?: number;
  verification_status?: string;
  warnings?: string[];
};

type EscapeResult = {
  success: boolean;
  user_location: { latitude: number; longitude: number };
  user_inside_detected_water: boolean;
  water_extent?: { type: string; coordinates: unknown } | null;
  flood_boundary?: { type: string; coordinates: unknown } | null;
  safety_offset_m: number;
  candidate_count: number;
  candidates: EscapeCandidate[];
  scene?: { image_id?: string | null; date?: string | null; cloud_cover?: number | null };
  message?: string;
  verification_status?: string;
  warnings?: string[];
};

export default function EvacuationPointPage() {
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<EscapeResult | null>(null);

  const analyzeEscape = async () => {
    if (!latitude.trim() || !longitude.trim()) {
      setError("Enter the latitude and longitude of the location to analyze.");
      return;
    }

    const lat = Number(latitude);
    const lon = Number(longitude);

    if (!Number.isFinite(lat) || lat < -90 || lat > 90) {
      setError("Enter a valid latitude between -90 and 90.");
      return;
    }
    if (!Number.isFinite(lon) || lon < -180 || lon > 180) {
      setError("Enter a valid longitude between -180 and 180.");
      return;
    }

    try {
      setLoading(true);
      setError("");
      setResult(null);

      const response = await fetch("http://127.0.0.1:8000/evacuation/escape", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          latitude: lat,
          longitude: lon,
          radius_m: 3000,
          safety_offset_m: 500,
          max_cloud_cover: 20,
          max_candidates: 5,
        }),
      });

      const data = await response.json();
      console.log("USER LOCATION:", data.user_location);
console.log("CANDIDATE COORDINATES:", data.candidates);
console.log("WATER EXTENT:", data.water_extent);
console.log("FLOOD BOUNDARY:", data.flood_boundary);
      if (!response.ok) {
        throw new Error(data?.detail || "Flood Escape analysis failed.");
      }
      setResult(data as EscapeResult);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not run evacuation analysis."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#0b1020] text-white">
      <header className="border-b border-white/10 px-5 py-5 md:px-8">
        <button
          type="button"
          onClick={() => (window.location.href = "/")}
          className="mb-4 text-sm text-cyan-300 hover:text-cyan-200"
        >
          ← Back to Geo-Insight
        </button>
        <h1 className="text-2xl font-semibold">🧭 Evacuation Point Analysis</h1>
        <p className="mt-1 text-sm text-slate-400">
          Inspect satellite-detected water extent and identify candidate points beyond the detected water boundary.
        </p>
      </header>

      <div className="mx-auto max-w-6xl space-y-7 p-5 md:p-8">
        <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 md:p-6">
          <h2 className="text-lg font-semibold">Location input</h2>
          <p className="mt-1 text-sm text-slate-400">
            Enter the coordinates of the person’s current location. The analysis checks the surrounding area using the available satellite scene.
          </p>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <label className="block text-sm text-slate-300">
              Latitude
              <input
                type="number"
                step="any"
                value={latitude}
                onChange={(e) => setLatitude(e.target.value)}
                placeholder="e.g. 12.9716"
                className="mt-2 w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white outline-none focus:border-cyan-500"
              />
            </label>
            <label className="block text-sm text-slate-300">
              Longitude
              <input
                type="number"
                step="any"
                value={longitude}
                onChange={(e) => setLongitude(e.target.value)}
                placeholder="e.g. 77.5946"
                className="mt-2 w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-white outline-none focus:border-cyan-500"
              />
            </label>
          </div>

          <button
            type="button"
            onClick={analyzeEscape}
            disabled={loading}
            className="mt-5 w-full rounded-lg bg-cyan-700 px-4 py-3 font-medium transition hover:bg-cyan-600 disabled:opacity-50"
          >
            {loading ? "Analyzing satellite data..." : "Find Evacuation Points"}
          </button>

          {error && (
            <p className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
              {error}
            </p>
          )}
        </section>

        {result && (
          <section className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-slate-400">Satellite scene date</p>
                <p className="mt-1 font-semibold">{result.scene?.date ?? "Unknown"}</p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-slate-400">Cloud cover</p>
                <p className="mt-1 font-semibold">
                  {result.scene?.cloud_cover != null
                    ? `${(result.scene.cloud_cover * 100).toFixed(2)}%`
                    : "Unknown"}
                </p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-slate-400">Candidate points</p>
                <p className="mt-1 font-semibold">{result.candidate_count}</p>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                <p className="text-xs text-slate-400">Safety offset used</p>
                <p className="mt-1 font-semibold">{result.safety_offset_m} m</p>
              </div>
            </div>

            <div className="h-[560px] overflow-hidden rounded-2xl border border-white/10">
              <FloodEscapeMap
                userLocation={result.user_location}
                waterExtent={result.water_extent ?? null}
                floodBoundary={result.flood_boundary ?? null}
                candidates={result.candidates ?? []}
              />
            </div>

            <p className="text-xs text-slate-400">
              Map key: blue fill = water-classified pixels; orange line = detected water boundary; marker = submitted location; candidate markers = proposed dry-side points; dashed yellow lines = straight-line references, not navigable routes.
            </p>

            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 md:p-6">
              <h2 className="text-lg font-semibold">Analysis details</h2>
              <p className="mt-2 text-sm text-slate-300">{result.message}</p>
              <p className="mt-2 text-sm text-slate-300">
                User inside detected water: {result.user_inside_detected_water ? "Yes" : "No"}
              </p>
              <p className="mt-1 text-sm text-slate-300">
                Verification status: {result.verification_status ?? "Unverified"}
              </p>

              {result.warnings?.length ? (
                <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-amber-200">
                  {result.warnings.map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              ) : null}

              {result.candidates?.length > 0 ? (
                <div className="mt-6 space-y-3">
                  <h3 className="font-semibold">Candidate evacuation points</h3>
                  {result.candidates.map((candidate, index) => (
                    <div
                      key={`${candidate.latitude}-${candidate.longitude}`}
                      className="rounded-xl border border-white/10 bg-black/10 p-4 text-sm text-slate-300"
                    >
                      <p className="font-semibold text-white">Candidate {index + 1}</p>
                      <p className="mt-1">
                        Coordinates: {candidate.latitude.toFixed(6)}, {candidate.longitude.toFixed(6)}
                      </p>
                      <p>
                        Straight-line distance: {candidate.distance_from_user_m?.toFixed(0) ?? "—"} m
                      </p>
                      <p className="text-amber-200">
                        {candidate.verification_status ?? "Unverified"}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-4 text-sm text-slate-400">
                  No candidate points were generated for this location.
                </p>
              )}
            </div>

            <p className="text-xs text-amber-200">
              Important: these are satellite-mask-checked candidate points, not confirmed safe shelters or verified road-accessible evacuation destinations. Water classification may include permanent water bodies.
            </p>
          </section>
        )}
      </div>
    </main>
  );
}
