import numpy as np
import rasterio

from flood.preprocessing import (
    load_flood_bands,
    get_flood_raster_metadata,
)

from flood.flood_detection import detect_flood
from flood.route_risk import calculate_route_risk
from flood.geocoding import geocode_location
from flood.routing import calculate_route
from dotenv import load_dotenv

load_dotenv()
IMAGE_DIR = "flood_data"

# Change these to your actual test locations
ROUTE_QUERY = "Mumbai Airport -> Andheri East"


print("======================================")
print("     FLOOD ROUTE RISK TEST")
print("======================================")


# --------------------------------------------------
# 1. Satellite
# --------------------------------------------------

print("\nLoading satellite data...")

image = load_flood_bands(
    IMAGE_DIR,
    normalize=False,
)

print("Satellite shape:", image.shape)


# --------------------------------------------------
# 2. Flood detection
# --------------------------------------------------

print("\nDetecting flood/water...")

flood_mask, mndwi = detect_flood(
    image,
    threshold=0.0,
)

print(
    "Flood pixels:",
    int(np.sum(flood_mask))
)

print(
    f"Flood area: "
    f"{np.mean(flood_mask) * 100:.2f}%"
)


# --------------------------------------------------
# 3. Raster metadata
# --------------------------------------------------

metadata = get_flood_raster_metadata(
    IMAGE_DIR
)

print(
    "Raster CRS:",
    metadata["crs"]
)


# --------------------------------------------------
# 4. Get TomTom route
# --------------------------------------------------

print("\nGetting TomTom route...")

origin_query, destination_query = ROUTE_QUERY.split("->", 1)

origin = geocode_location(origin_query.strip())
destination = geocode_location(destination_query.strip())

route_result = calculate_route(
    origin,
    destination,
)

print(
    "Routes returned:",
    len(route_result["routes"])
)


# --------------------------------------------------
# 5. Evaluate every candidate route
# --------------------------------------------------

route_results = []

for route in route_result["routes"]:

    print(
        f"\nEvaluating route "
        f"{route['route_id']}..."
    )

    # TomTom path is a GeoJSON-style LineString
    path = route["path"]

    if isinstance(path, dict):
        coordinates = path["coordinates"]
    else:
        coordinates = path

    risk = calculate_route_risk(
        route_coordinates=coordinates,
        flood_mask=flood_mask,
        transform=metadata["transform"],
        crs=metadata["crs"],
    )

    result = {
        "route_id": route["route_id"],
        "summary": route["summary"],
        **risk,
    }

    route_results.append(result)


# --------------------------------------------------
# 6. Print results
# --------------------------------------------------

print("\n")
print("======================================")
print("          ROUTE RISK RESULTS")
print("======================================")

for result in route_results:

    print(
        f"\nRoute {result['route_id']}"
    )

    print(
        f"Length: "
        f"{result['route_length_m']:.2f} m"
    )

    print(
        f"Flooded length: "
        f"{result['flooded_length_m']:.2f} m"
    )

    print(
        f"Flooded percentage: "
        f"{result['flooded_percentage']:.2f}%"
    )

    print(
        f"Risk: "
        f"{result['risk'].upper()}"
    )


# --------------------------------------------------
# 7. Select safest route
# --------------------------------------------------

valid_routes = [
    r for r in route_results
    if r["risk"] != "unknown"
]

if valid_routes:

    safest_route = min(
        valid_routes,
        key=lambda r: r["flooded_percentage"]
    )

    print("\n")
    print("======================================")
    print("          SAFEST ROUTE")
    print("======================================")

    print(
        "Selected route:",
        safest_route["route_id"]
    )

    print(
        f"Flooded percentage: "
        f"{safest_route['flooded_percentage']:.2f}%"
    )

    print(
        "Risk:",
        safest_route["risk"].upper()
    )