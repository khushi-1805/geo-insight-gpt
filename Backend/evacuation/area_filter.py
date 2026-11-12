from dataclasses import dataclass, field
from typing import Optional

from evacuation.dry_area_detector import DryArea
from evacuation.area_measurements import AreaMeasurements


@dataclass
class AreaCandidate:
    area: DryArea
    flood_fraction: Optional[float]
    building_fraction: Optional[float]
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def filter_area_candidates(
    areas: list[DryArea],
    measurements: list[AreaMeasurements],
    min_area_m2: float = 10_000,
    max_flood_fraction: float = 0.0,
    max_building_fraction: Optional[float] = 0.10,
) -> list[AreaCandidate]:
    """Filter candidates. Informational warnings do not automatically reject."""
    if len(areas) != len(measurements):
        raise ValueError("Each area must have exactly one corresponding measurement")
    if min_area_m2 <= 0:
        raise ValueError("min_area_m2 must be positive")
    if not 0 <= max_flood_fraction <= 1:
        raise ValueError("max_flood_fraction must be between 0 and 1")
    if (
        max_building_fraction is not None
        and not 0 <= max_building_fraction <= 1
    ):
        raise ValueError("max_building_fraction must be between 0 and 1")

    results = []
    for area, measurement in zip(areas, measurements):
        reasons: list[str] = []
        warnings = list(measurement.warnings)

        if area.area_m2 < min_area_m2:
            reasons.append("Area is below the minimum surface area")
        if not measurement.measurements_valid:
            reasons.append("Required spatial measurements are incomplete or invalid")

        flood_fraction = measurement.flood_fraction
        building_fraction = measurement.building_fraction

        if flood_fraction is None or not 0 <= flood_fraction <= 1:
            reasons.append("Flood exposure is missing or invalid")
        elif flood_fraction > max_flood_fraction:
            reasons.append("Flood exposure exceeds the configured limit")

        if building_fraction is None:
            reasons.append("Building coverage is unknown")
        elif not 0 <= building_fraction <= 1:
            reasons.append("Building coverage is invalid")
        elif (
            max_building_fraction is not None
            and building_fraction > max_building_fraction
        ):
            reasons.append("Building coverage exceeds the configured limit")

        results.append(
            AreaCandidate(
                area=area,
                flood_fraction=flood_fraction,
                building_fraction=building_fraction,
                eligible=not reasons,
                reasons=reasons,
                warnings=warnings,
            )
        )

    return sorted(results, key=lambda item: item.area.area_m2, reverse=True)
