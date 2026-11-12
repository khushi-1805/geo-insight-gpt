
from dataclasses import dataclass
from math import atan2, cos, degrees, radians, sin, sqrt
from typing import List

from evacuation.area_filter import AreaCandidate


@dataclass
class RankedDestination:
    candidate: AreaCandidate
    distance_m: float
    bearing_degrees: float
    direction: str


def haversine_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate straight-line distance between two geographic points."""
    earth_radius_m = 6_371_000

    lat1_rad, lat2_rad = radians(lat1), radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    )
    a = min(1.0, max(0.0, a))

    return 2 * earth_radius_m * atan2(sqrt(a), sqrt(1 - a))


def calculate_bearing_degrees(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate initial compass bearing from point 1 to point 2."""
    lat1_rad, lat2_rad = radians(lat1), radians(lat2)
    delta_lon = radians(lon2 - lon1)

    x = sin(delta_lon) * cos(lat2_rad)
    y = (
        cos(lat1_rad) * sin(lat2_rad)
        - sin(lat1_rad) * cos(lat2_rad) * cos(delta_lon)
    )

    return (degrees(atan2(x, y)) + 360) % 360


def compass_direction(bearing: float) -> str:
    """Convert a bearing to one of eight compass directions."""
    directions = [
        "N", "NE", "E", "SE",
        "S", "SW", "W", "NW",
    ]
    return directions[round(bearing / 45) % 8]


def rank_destinations(
    candidates: List[AreaCandidate],
    user_lat: float,
    user_lon: float,
    limit: int = 5,
) -> List[RankedDestination]:
    """
    Rank eligible destinations by straight-line distance.

    This does not establish that the destination is reachable or safe.
    """
    if not -90 <= user_lat <= 90:
        raise ValueError("Invalid user latitude")
    if not -180 <= user_lon <= 180:
        raise ValueError("Invalid user longitude")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    ranked = []

    for candidate in candidates:
        if not candidate.eligible:
            continue

        area = candidate.area
        distance = haversine_distance_m(
            user_lat, user_lon,
            area.center_lat, area.center_lon,
        )
        bearing = calculate_bearing_degrees(
            user_lat, user_lon,
            area.center_lat, area.center_lon,
        )

        ranked.append(
            RankedDestination(
                candidate=candidate,
                distance_m=distance,
                bearing_degrees=bearing,
                direction=compass_direction(bearing),
            )
        )

    ranked.sort(key=lambda item: item.distance_m)
    return ranked[:limit]
