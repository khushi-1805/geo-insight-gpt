from typing import Optional

from evacuation.area_filter import AreaCandidate
from evacuation.destination_ranker import rank_destinations
from evacuation.schemas import (
    DryAreaDestination,
    EvacuationSearchResponse,
    UserLocation,
)


def build_evacuation_response(
    user_lat: float,
    user_lon: float,
    candidates: list[AreaCandidate],
    flood_data_timestamp: Optional[str] = None,
    model_name: Optional[str] = None,
    limit: int = 5,
) -> EvacuationSearchResponse:
    """Format ranked candidates; this does not certify safety or access."""
    ranked = rank_destinations(candidates, user_lat, user_lon, limit)
    destinations = []

    for index, item in enumerate(ranked, start=1):
        candidate = item.candidate
        area = candidate.area
        destinations.append(
            DryAreaDestination(
                destination_id=f"candidate-{index}",
                latitude=area.center_lat,
                longitude=area.center_lon,
                area_m2=area.area_m2,
                distance_m=round(item.distance_m, 2),
                bearing_degrees=round(item.bearing_degrees, 2),
                direction=item.direction,
                flood_fraction=candidate.flood_fraction,
                building_fraction=candidate.building_fraction,
                verification_status="unverified",
                warnings=[
                    "This is a satellite-derived candidate area, not a confirmed shelter.",
                    "Straight-line distance does not establish safe accessibility.",
                    *candidate.warnings,
                    *candidate.reasons,
                ],
            )
        )

    message = (
        "Candidate areas are ranked by straight-line distance. "
        "Their suitability, current conditions and accessibility require verification."
        if destinations
        else (
            "No eligible candidate areas are available. "
            "Complete flood and building-footprint measurements are required."
        )
    )
    return EvacuationSearchResponse(
        user_location=UserLocation(latitude=user_lat, longitude=user_lon),
        destinations=destinations,
        flood_data_timestamp=flood_data_timestamp,
        model_name=model_name,
        message=message,
    )
