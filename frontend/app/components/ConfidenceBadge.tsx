type ConfidenceLevel = "high" | "medium" | "low" | string | undefined;

export function confidenceFromPercentage(
  percentage?: number
): "high" | "medium" | "low" | undefined {
  if (percentage === undefined || Number.isNaN(percentage)) {
    return undefined;
  }

  if (percentage < 40) {
    return "low";
  }

  if (percentage < 70) {
    return "medium";
  }

  return "high";
}

export default function ConfidenceBadge({
  confidence,
  percentage,
}: {
  confidence?: ConfidenceLevel;
  percentage?: number;
}) {
  const level =
    confidence || confidenceFromPercentage(percentage);

  if (!level) {
    return null;
  }

  const styles =
    level === "high"
      ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-300"
      : level === "medium"
        ? "border-amber-400/25 bg-amber-400/10 text-amber-300"
        : "border-rose-400/25 bg-rose-400/10 text-rose-300";

  const label = level.charAt(0).toUpperCase() + level.slice(1);

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${styles}`}
      title={
        percentage !== undefined
          ? `${percentage.toFixed(1)}% valid (cloud-free) pixels`
          : "Derived from valid-pixel coverage after SCL masking"
      }
    >
      {label}
      {percentage !== undefined ? ` · ${percentage.toFixed(0)}%` : ""}
    </span>
  );
}
