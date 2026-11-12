"""Sentinel-2 L2A search and route-corridor band download utilities."""

import os
from concurrent.futures import ThreadPoolExecutor

import planetary_computer
import pystac_client
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from rasterio.windows import Window, from_bounds
from shapely.geometry import shape

PLANETARY_COMPUTER_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
SENTINEL2_COLLECTION = "sentinel-2-l2a"

# Keep this order in sync with preprocessing.py and flood_detection.py.
FLOOD_BANDS = ["B02", "B03", "B04", "B8A", "B11", "B12"]


def search_satellite_images(
    possible_route_area,
    start_date,
    end_date,
    max_cloud_cover=20,
):
    """Find recent Sentinel-2 L2A scenes intersecting the route corridor."""
    if not possible_route_area:
        raise ValueError("Possible route area is required.")
    if not start_date or not end_date:
        raise ValueError("Both start_date and end_date are required.")
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")

    catalog = pystac_client.Client.open(
        PLANETARY_COMPUTER_URL,
        modifier=planetary_computer.sign_inplace,
    )
    search = catalog.search(
        collections=[SENTINEL2_COLLECTION],
        intersects=possible_route_area,
        datetime=f"{start_date}/{end_date}",
        query={"eo:cloud_cover": {"lte": max_cloud_cover}},
    )

    items = list(search.items())
    print(f"Sentinel-2 L2A scenes found before validation: {len(items)}")

    results = []
    for item in items:
        cloud_cover = item.properties.get("eo:cloud_cover")
        if cloud_cover is not None and cloud_cover > max_cloud_cover:
            continue

        assets = {}
        for band in FLOOD_BANDS:
            asset = item.assets.get(band)
            if asset is not None:
                assets[band] = asset.href

        missing = [band for band in FLOOD_BANDS if band not in assets]
        if missing:
            print(f"Skipping {item.id}; missing bands: {', '.join(missing)}")
            continue

        results.append({
            "id": item.id,
            "date": item.datetime.isoformat() if item.datetime else None,
            "cloud_cover": cloud_cover,
            "assets": assets,
        })

    # Prefer the most recent usable scene within the requested date window.
    results.sort(key=lambda scene: scene["date"] or "", reverse=True)
    print(f"Valid Sentinel-2 L2A scenes: {len(results)}")
    return results


def download_one_band(band, url, possible_route_area, output_dir):
    """Read only the route-corridor window from a Sentinel-2 COG and mask it."""
    output_path = os.path.join(output_dir, f"{band}.tif")
    with rasterio.open(url) as src:
        # Transform corridor geometry into the source raster's CRS.
        geometry = transform_geom("EPSG:4326", src.crs, possible_route_area)
        corridor_shape = shape(geometry)
        minx, miny, maxx, maxy = corridor_shape.bounds

        window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
        window = window.intersection(Window(0, 0, src.width, src.height))
        if window.width <= 0 or window.height <= 0:
            raise ValueError(
                f"Route corridor does not overlap the {band} raster. "
                f"Corridor bounds: {corridor_shape.bounds}; raster bounds: {src.bounds}"
            )

        data = src.read(1, window=window)
        if data.size == 0:
            raise ValueError(f"The clipped {band} raster is empty.")

        window_transform = src.window_transform(window)
        inside = geometry_mask(
            [geometry],
            out_shape=data.shape,
            transform=window_transform,
            invert=True,
        )

        # Zero is treated as nodata for pixels outside the corridor.
        data = data.copy()
        data[~inside] = 0

        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            height=data.shape[0],
            width=data.shape[1],
            transform=window_transform,
            nodata=0,
        )

        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(data, 1)

    print(f"Saved {band}: {output_path}")
    return band, output_path


def download_and_clip_bands(image, possible_route_area, output_dir="flood_data"):
    """Download and clip all six Sentinel-2 bands needed by the MNDWI detector."""
    if not image or not image.get("assets"):
        raise ValueError("A valid Sentinel-2 image with assets is required.")
    if not possible_route_area:
        raise ValueError("Possible route area is required.")

    assets = image["assets"]
    missing = [band for band in FLOOD_BANDS if band not in assets]
    if missing:
        raise ValueError(
            "Selected scene is missing required Sentinel-2 bands: "
            + ", ".join(missing)
        )

    os.makedirs(output_dir, exist_ok=True)

    # Remove stale files for the bands this detector consumes.
    for band in FLOOD_BANDS:
        old_path = os.path.join(output_dir, f"{band}.tif")
        if os.path.exists(old_path):
            os.remove(old_path)

    downloaded = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(
                download_one_band,
                band,
                assets[band],
                possible_route_area,
                output_dir,
            )
            for band in FLOOD_BANDS
        ]
        for future in futures:
            band, path = future.result()
            downloaded[band] = path

    if set(downloaded) != set(FLOOD_BANDS):
        raise RuntimeError("Not all required Sentinel-2 bands were downloaded.")

    return downloaded
