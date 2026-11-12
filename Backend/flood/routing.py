import json
import os
import time
import http.client
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .geocoding import geocode_location


TOMTOM_ROUTING_URL = (
    "https://api.tomtom.com/maps/orbis/routing/routes/calculate"
)


def geocode_route_locations(route_query: str):
    """
    Parse an origin -> destination query and geocode both locations.
    """

    if "->" not in route_query:
        raise ValueError(
            "Please provide the route in this format: "
            "Origin -> Destination"
        )

    origin_query, destination_query = route_query.split(
        "->",
        1
    )

    origin_query = origin_query.strip()
    destination_query = destination_query.strip()

    if not origin_query:
        raise ValueError("Origin cannot be empty.")

    if not destination_query:
        raise ValueError("Destination cannot be empty.")

    origin = geocode_location(origin_query)
    destination = geocode_location(destination_query)

    return {
        "origin": origin,
        "destination": destination,
    }


def calculate_route(origin, destination):
    """
    Calculate a road route between two geocoded locations
    using TomTom Routing API v3.
    """

    api_key = os.getenv("GEOENCODINGAPI")

    if not api_key:
        raise RuntimeError(
            "GEOENCODINGAPI is not set in the environment."
        )

    request_body = {
    "routePlanningLocations": {
        "origin": {
            "type": "Point",
            "coordinates": [
                origin["longitude"],
                origin["latitude"],
            ],
        },
        "destination": {
            "type": "Point",
            "coordinates": [
                destination["longitude"],
                destination["latitude"],
            ],
        },
    },
    "routeType": "fast",
    "traffic": "live",
    "travelMode": "car",
    "maxPathAlternativeRoutes": 2,
    "guidance": "instructions",
    "instructionPhonetics": "ipa",
}

    url = f"{TOMTOM_ROUTING_URL}?apiVersion=3"

    headers = {
        "TomTom-Api-Key": api_key,
        "TomTom-Api-Version": "3",
        "Attributes": "routes",
        "Content-Type": "application/json",
        "Accept": "application/json",
"Accept-Language": "en-GB",
    }
    request = Request(
        url,
        data=json.dumps(request_body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    # Retry the entire request if the connection drops while the
    # response body is being downloaded. Re-reading the same response
    # cannot recover bytes that were never received.
    max_attempts = 3
    data = None

    for attempt in range(max_attempts):
        try:
            with urlopen(request, timeout=60) as response:
                response_text = response.read().decode("utf-8")

            data = json.loads(response_text)
            break

        except HTTPError as error:
            # HTTPError is also a URLError, so handle it first.
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"TomTom routing error {error.code}: {body}"
            ) from error

        except (
            http.client.IncompleteRead,
            URLError,
            TimeoutError,
            ConnectionError,
            json.JSONDecodeError,
        ) as error:
            if attempt == max_attempts - 1:
                if isinstance(error, URLError):
                    detail = error.reason
                else:
                    detail = str(error)

                raise RuntimeError(
                    f"TomTom routing request failed after "
                    f"{max_attempts} attempts: {detail}"
                ) from error

            delay = 2 ** attempt
            print(
                f"TomTom response failed on attempt "
                f"{attempt + 1}/{max_attempts}: {error}. "
                f"Retrying in {delay}s..."
            )
            time.sleep(delay)

    if data is None:
        raise RuntimeError("TomTom routing returned no response data.")

    routes = data.get("routes", [])

    if not routes:
        raise ValueError(
            "TomTom did not return a route."
        )

    route = routes[0]

    print("\n===== TOMTOM ROUTE RESPONSE =====")
    print(json.dumps(route, indent=2))
    print("=================================\n")

    legs = route.get("legs", [])

    if not legs:
        raise ValueError(
            "TomTom did not return route legs."
        )

    candidate_routes = []

    for index, route in enumerate(routes):
        legs = route.get("legs", [])

        if not legs:
            continue

        path = legs[0].get("path")

        if not path:
            continue

        candidate_routes.append({
    "route_id": index,
    "summary": route.get("summary"),
    "path": path,
    "instructions": route.get("instructions", []),
})

    if not candidate_routes:
        raise ValueError(
            "TomTom did not return usable route geometry."
        )

    return {
        "routes": candidate_routes
    }