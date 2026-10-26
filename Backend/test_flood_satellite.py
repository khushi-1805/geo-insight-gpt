from flood.satellite import search_satellite_images
from flood.corridor import create_route_corridor
from flood.routing import geocode_route_locations, calculate_route
from dotenv import load_dotenv
from flood.satellite import (
    search_satellite_images,
    download_and_clip_bands,
)
load_dotenv()

def main():
    query = (
        "Chhatrapati Shivaji Maharaj International Airport, Mumbai"
        " -> "
        "Andheri East, Mumbai"
    )

    # 1. Geocode
    locations = geocode_route_locations(query)

    # 2. Get routes
    route_result = calculate_route(
        locations["origin"],
        locations["destination"],
    )

    # 3. Create route corridor
    possible_route_area = create_route_corridor(
        route_result["routes"]
    )

    # 4. Search Sentinel-2
    images = search_satellite_images(
        possible_route_area=possible_route_area,
        start_date="2026-01-01",
        end_date="2026-08-22",
        max_cloud_cover=20,
    )

    print("\n===== SATELLITE SEARCH =====")

    print("Images found:", len(images))
    if not images:
      raise RuntimeError("No suitable satellite images found.")

    best_image = images[0]

    print("\n===== SELECTED IMAGE =====")
    print("ID:", best_image["id"])
    print("Date:", best_image["date"])
    print("Cloud cover:", best_image["cloud_cover"])

    print("\nAvailable flood bands:")
    for band in best_image["assets"]:
        print("-", band)

    downloaded = download_and_clip_bands(
        image=best_image,
        possible_route_area=possible_route_area,
    )

    print("\n===== DOWNLOADED BANDS =====")

    for band, path in downloaded.items():
        print(band, "->", path)

    print("============================")

    for image in images[:5]:
        print("\nID:", image["id"])
        print("Date:", image["date"])
        print("Cloud cover:", image["cloud_cover"])

    print("============================")


if __name__ == "__main__":
    main()