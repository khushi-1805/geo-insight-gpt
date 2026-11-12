
from typing import List, Optional

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
    candidates: List[AreaCandidate],
    flood_data_timestamp: Optional[str] = None,
    model_name: Optional[str] = None,
    limit: int = 5,
) -> EvacuationSearchResponse:
    """
    Format ranked candidates for the frontend.

    Input candidates must already have been evaluated using real,
    spatially measured flood and building data. This function does
    not determine whether a location is safe or reachable.
    """
    ranked = rank_destinations(
        candidates=candidates,
        user_lat=user_lat,
        user_lon=user_lon,
        limit=limit,
    )

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
                    "Candidate dry area; not a confirmed evacuation shelter.",
                    "Straight-line distance does not establish safe accessibility.",
                    *candidate.reasons,
                ],
            )
        )

    if destinations:
        message = (
            "Candidate areas are ranked by straight-line distance. "
            "Their suitability and accessibility require verification."
        )
    else:
        message = (
            "No eligible candidate areas are available. "
            "Flood and land-cover measurements must be validated "
            "before recommendations can be made."
        )

    return EvacuationSearchResponse(
        user_location=UserLocation(
            latitude=user_lat,
            longitude=user_lon,
        ),
        destinations=destinations,
        flood_data_timestamp=flood_data_timestamp,
        model_name=model_name,
        message=message,
    )
