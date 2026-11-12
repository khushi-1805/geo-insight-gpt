
from dataclasses import dataclass
from typing import List, Optional

from evacuation.dry_area_detector import DryArea


@dataclass
class AreaMeasurements:
    """Measured spatial properties of one candidate area."""

    flood_fraction: Optional[float]
    building_fraction: Optional[float]
    measurements_valid: bool
    warnings: List[str]


@dataclass
class AreaCandidate:
    area: DryArea
    flood_fraction: Optional[float]
    building_fraction: Optional[float]
    eligible: bool
    reasons: List[str]


def filter_area_candidates(
    areas: List[DryArea],
    measurements: List[AreaMeasurements],
    min_area_m2: float = 10_000,
    max_flood_fraction: float = 0.0,
    max_building_fraction: Optional[float] = 0.10,
) -> List[AreaCandidate]:
    """
    Filter detected areas using explicitly supplied measurements.

    Measurements must correspond to areas in the same order.
    Missing or invalid measurements never qualify an area.
    """
    if len(areas) != len(measurements):
        raise ValueError(
            "Each area must have exactly one corresponding measurement"
        )

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
        reasons = list(measurement.warnings)

        if area.area_m2 < min_area_m2:
            reasons.append("Area is below the minimum surface area")

        if not measurement.measurements_valid:
            reasons.append("Spatial measurements are not validated")

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

        eligible = not reasons

        results.append(
            AreaCandidate(
                area=area,
                flood_fraction=flood_fraction,
                building_fraction=building_fraction,
                eligible=eligible,
                reasons=reasons,
            )
        )

    return sorted(
        results,
        key=lambda candidate: candidate.area.area_m2,
        reverse=True,
    )
