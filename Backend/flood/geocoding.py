import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


TOMTOM_GEOCODE_URL = (
    "https://api.tomtom.com/maps/orbis/places/geocode"
)


def geocode_location(query: str):
    """
    Convert a human-readable location into coordinates.

    Returns:
        {
            "query": "...",
            "title": "...",
            "latitude": ...,
            "longitude": ...,
            "type": "...",
            "address": {...}
        }
    """

    api_key = os.getenv("GEOENCODINGAPI")

    if not api_key:
        raise RuntimeError(
            "GEOENCODINGAPI is not set in the environment."
        )

    params = {
        "query": query,
        "countryCodesIso2": "IN",
        "maxResults": 5,
    }

    url = f"{TOMTOM_GEOCODE_URL}?{urlencode(params)}"

    headers = {
        "TomTom-Api-Key": api_key,
        "TomTom-Api-Version": "2",
        "Attributes": "results(title,type,position,address)",
        "Accept": "application/json",
    }

    request = Request(
        url,
        headers=headers,
        method="GET",
    )

    try:
        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))

    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"TomTom API error {error.code}: {body}"
        )

    except URLError as error:
        raise RuntimeError(
            f"Could not connect to TomTom: {error.reason}"
        )

    results = data.get("results", [])

    if not results:
        raise ValueError(
            f"No location found for '{query}'."
        )

    result = results[0]

    coordinates = (
        result
        .get("position", {})
        .get("coordinates")
    )

    if not coordinates or len(coordinates) < 2:
        raise ValueError(
            f"TomTom returned a result without coordinates "
            f"for '{query}'."
        )

    longitude = coordinates[0]
    latitude = coordinates[1]

    return {
        "query": query,
        "title": result.get("title"),
        "type": result.get("type"),
        "latitude": latitude,
        "longitude": longitude,
        "address": result.get("address", {}),
    }