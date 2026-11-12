import math
from typing import Any


EARTH_RADIUS_METERS = 6_371_000


def calculate_direct_direction(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> dict[str, float | str]:
    """
    Calculate straight-line distance and compass bearing between two
    geographic coordinates.

    This does not calculate a walkable or drivable route.
    """

    lat1 = math.radians(origin_latitude)
    lon1 = math.radians(origin_longitude)
    lat2 = math.radians(destination_latitude)
    lon2 = math.radians(destination_longitude)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    haversine_a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    haversine_a = min(1.0, max(0.0, haversine_a))
    central_angle = 2 * math.atan2(
        math.sqrt(haversine_a),
        math.sqrt(1 - haversine_a),
    )

    distance_m = round(EARTH_RADIUS_METERS * central_angle)

    y = math.sin(delta_lon) * math.cos(lat2)
    x = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    )

    bearing_degrees = (math.degrees(math.atan2(y, x)) + 360) % 360

    compass_directions = [
        "N", "NE", "E", "SE",
        "S", "SW", "W", "NW",
    ]
    direction = compass_directions[
        int((bearing_degrees + 22.5) // 45) % 8
    ]

    return {
        "distance_from_user_m": distance_m,
        "direction_from_user": direction,
        "bearing_degrees": round(bearing_degrees, 1),
    }


def add_direct_directions(result: dict[str, Any]) -> dict[str, Any]:
    """
    Add straight-line distance and compass direction to every evacuation
    candidate using result['user_location'].

    Expected user_location and candidate coordinate keys:
    latitude, longitude.
    """

    user_location = result.get("user_location")
    candidates = result.get("candidates", [])

    if not isinstance(user_location, dict):
        raise ValueError(
            "Flood escape analysis did not return a valid user_location."
        )

    try:
        user_latitude = float(user_location["latitude"])
        user_longitude = float(user_location["longitude"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "user_location must contain numeric latitude and longitude."
        ) from error

    for index, candidate in enumerate(candidates):
        try:
            destination_latitude = float(candidate["latitude"])
            destination_longitude = float(candidate["longitude"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Evacuation candidate {index + 1} has invalid coordinates."
            ) from error

        guidance = calculate_direct_direction(
            user_latitude,
            user_longitude,
            destination_latitude,
            destination_longitude,
        )

        # Preserve the existing distance_from_user_m field name so older
        # frontend code can continue reading it.
        candidate.update(guidance)

    result["direction_method"] = "straight_line_compass_bearing"
    result.setdefault("warnings", []).append(
        "Distances and directions are straight-line estimates, not "
        "walkable routes. The connecting map line does not indicate "
        "physical accessibility or safety."
    )

    return result
