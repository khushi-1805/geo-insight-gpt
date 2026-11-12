from datetime import date, timedelta
from pathlib import Path
import uuid

from .geocoding import geocode_location
from .routing import calculate_route
from .corridor import create_route_corridor
from .satellite import (
    search_satellite_images,
    download_and_clip_bands,
)
from .preprocessing import (
    load_flood_bands,
    get_flood_raster_metadata,
)
from .flood_detection import detect_flood
from .route_risk import calculate_route_risk


def run_flood_analysis(
    origin_query,
    destination_query,
    start_date=None,
    end_date=None,
):
    """
    Complete flood-safe-route pipeline.

    Origin + Destination
        -> Geocoding
        -> TomTom routes
        -> Route corridor
        -> Sentinel-2 search
        -> Satellite download
        -> Flood detection
        -> Route risk
        -> Safest route
    """

    print("\n======================================")
    print("       FLOOD RESCUE ANALYSIS")
    print("======================================")

    # --------------------------------------------------
    # 1. Geocode
    # --------------------------------------------------

    print("\n[1] Geocoding locations...")

    origin = geocode_location(origin_query)
    destination = geocode_location(destination_query)

    print("Origin:", origin)
    print("Destination:", destination)

    # --------------------------------------------------
    # 2. TomTom routes
    # --------------------------------------------------

    print("\n[2] Calculating routes...")

    route_result = calculate_route(
        origin,
        destination,
    )

    print(
        "Routes found:",
        len(route_result["routes"])
    )

    # --------------------------------------------------
    # 3. Create route corridor
    # --------------------------------------------------

    print("\n[3] Creating route corridor...")

    possible_route_area = create_route_corridor(
        route_result["routes"]
    )

    # --------------------------------------------------
    # 4. Satellite search
    # --------------------------------------------------

    print("\n[4] Searching Sentinel-2...")

    if start_date is None:
        start_date = (
            date.today() - timedelta(days=180)
        ).isoformat()

    if end_date is None:
        end_date = date.today().isoformat()

    satellite_images = search_satellite_images(
        possible_route_area,
        start_date,
        end_date,
        max_cloud_cover=20,
    )

    if not satellite_images:
        raise ValueError(
            "No suitable Sentinel-2 images were found "
            "for this route corridor."
        )

    # satellite.py returns the newest valid scene first within the
    # requested date window and cloud-cover limit.
    selected_image = satellite_images[0]

    print("\nSelected satellite image:")
    print("ID:", selected_image["id"])
    print("Date:", selected_image["date"])
    print(
        "Cloud cover:",
        selected_image["cloud_cover"],
    )

    # A unique directory prevents old rasters from a previous request
    # from being accidentally loaded into this analysis.
    output_dir = str(Path("flood_data") / f"run_{uuid.uuid4().hex[:12]}")

    # --------------------------------------------------
    # 5. Download and clip satellite bands
    # --------------------------------------------------

    print("\n[5] Downloading satellite bands...")

    downloaded_bands = download_and_clip_bands(
        selected_image,
        possible_route_area,
        output_dir=output_dir,
    )

    # --------------------------------------------------
    # 6. Load satellite image
    # --------------------------------------------------

    print("\n[6] Loading satellite data...")

    image = load_flood_bands(
        output_dir,
        normalize=False,
    )

    # --------------------------------------------------
    # 7. Detect flood / water
    # --------------------------------------------------

    print("\n[7] Detecting flood/water...")

    flood_mask, mndwi = detect_flood(
        image,
        threshold=0.0,
    )

    flood_area_percentage = (
        float(flood_mask.mean()) * 100
    )

    print(
        f"Detected water/flood area: "
        f"{flood_area_percentage:.2f}%"
    )

    # --------------------------------------------------
    # 8. Raster metadata
    # --------------------------------------------------

    metadata = get_flood_raster_metadata(output_dir)

    # --------------------------------------------------
    # 9. Calculate risk for every route
    # --------------------------------------------------

    print("\n[8] Calculating route risks...")

    analyzed_routes = []

    for route in route_result["routes"]:

        path = route["path"]

        coordinates = path["coordinates"]

        risk = calculate_route_risk(
            route_coordinates=coordinates,
            flood_mask=flood_mask,
            transform=metadata["transform"],
            crs=metadata["crs"],
        )

        analyzed_routes.append({
    "route_id": route["route_id"],
    "summary": route["summary"],
    "path": coordinates,
    "instructions": route.get("instructions", []),
    "flood_risk": risk,
})

        if risk["risk"] == "unknown":
            print(
                f"Route {route['route_id']}: UNKNOWN "
                f"(raster coverage {risk.get('coverage_percentage', 0):.2f}%)"
            )
        else:
            print(
                f"Route {route['route_id']}: "
                f"{risk['flooded_percentage']:.2f}% "
                f"flood overlap -> {risk['risk']} "
                f"(raster coverage {risk.get('coverage_percentage', 100):.2f}%)"
            )

    # --------------------------------------------------
    # 10. Select safest route
    # --------------------------------------------------

    valid_routes = [
        route
        for route in analyzed_routes
        if route["flood_risk"]["risk"] != "unknown"
    ]

    safest_route = None

    if valid_routes:
        safest_route = min(
            valid_routes,
            key=lambda route:
                route["flood_risk"]["flooded_percentage"],
        )

    print("\n======================================")

    if safest_route:
        print(
            "Safest route:",
            safest_route["route_id"],
        )
        print(
            "Risk:",
            safest_route["flood_risk"]["risk"],
        )
        print(
            "Flood overlap:",
            safest_route["flood_risk"][
                "flooded_percentage"
            ],
            "%",
        )
    else:
        print("No route could be evaluated.")

    print("======================================")

    # --------------------------------------------------
    # 11. Return result
    # --------------------------------------------------

    return {
        "success": True,

        "origin": {
            "query": origin_query,
            **origin,
        },

        "destination": {
            "query": destination_query,
            **destination,
        },

        "satellite": {
            "image_id": selected_image["id"],
            "date": selected_image["date"],
            "cloud_cover": selected_image["cloud_cover"],
            "flood_area_percentage":
                round(flood_area_percentage, 2),
            "crs": str(metadata["crs"]),
        },

        "routes": analyzed_routes,

        "safest_route": (
            {
                "route_id":
                    safest_route["route_id"],
                "flood_risk":
                    safest_route["flood_risk"],
            }
            if safest_route
            else None
        ),
    }