
from datetime import date, timedelta

from shapely.geometry import mapping, Point

from flood.satellite import search_satellite_images


import os

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import reproject, transform_geom
from rasterio.enums import Resampling

from pathlib import Path
import uuid

from flood.satellite import download_and_clip_bands
from flood.preprocessing import load_flood_bands, get_flood_raster_metadata
from flood.flood_detection import detect_flood

from evacuation.dry_area_detector import detect_large_dry_areas

from flood.preprocessing import FLOOD_BANDS

def detect_evacuation_dry_areas(
    latitude: float,
    longitude: float,
    radius_m: float = 3000,
    min_area_m2: float = 10000,
    start_date: str | None = None,
    end_date: str | None = None,
    max_cloud_cover: float = 20,
) -> dict:
    """
    Find candidate dry areas around a user using Sentinel-2 imagery.

    This produces unverified candidates, not confirmed safe destinations.
    """
    result = find_evacuation_satellite_scene(
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=max_cloud_cover,
    )

    search_area = result["search_area"]
    scene = result["scene"]

    data_dir = str(
        Path("evacuation_data") / f"run_{uuid.uuid4().hex[:12]}"
    )

    download_and_clip_bands(
        image=scene,
        possible_route_area=search_area,
        output_dir=data_dir,
    )

    valid_mask = build_valid_pixel_mask(
        data_dir=data_dir,
        search_area=search_area,
    )

    if not valid_mask.any():
        raise ValueError(
            "No valid satellite pixels cover the evacuation search area."
        )

    image = load_flood_bands(
        data_dir=data_dir,
        normalize=False,
    )

    flood_mask, mndwi = detect_flood(
        image,
        threshold=0.0,
    )

    metadata = get_flood_raster_metadata(data_dir)

    if flood_mask.shape != valid_mask.shape:
        raise ValueError(
            "Flood mask and validity mask have different shapes."
        )

    dry_areas = detect_large_dry_areas(
        flood_mask=flood_mask,
        transform=metadata["transform"],
        crs=metadata["crs"],
        min_area_m2=min_area_m2,
        valid_mask=valid_mask,
    )

    return {
        "success": True,
        "scene": {
            "image_id": scene["id"],
            "date": scene["date"],
            "cloud_cover": scene["cloud_cover"],
        },
        "search_radius_m": radius_m,
        "valid_pixel_count": int(valid_mask.sum()),
        "candidate_count": len(dry_areas),
        "candidates": dry_areas,
        "verification_status": "unverified",
        "warnings": [
            "Water detection uses the existing MNDWI threshold.",
            "Detected dry areas are not confirmed evacuation shelters.",
            "Satellite imagery may not reflect current flood conditions.",
            "Cloud and cloud-shadow contamination is not fully assessed.",
            "Building coverage and safe accessibility are not yet verified.",
        ],
    }

def build_valid_pixel_mask(data_dir: str, search_area: dict) -> np.ndarray:
    """
    Return a boolean mask on the B02 reference grid.

    True means the pixel is inside the search geometry and
    is valid in every required Sentinel-2 band.
    """
    reference_path = os.path.join(data_dir, "B02.tif")

    if not os.path.exists(reference_path):
        raise FileNotFoundError(
            f"Reference raster not found: {reference_path}"
        )

    with rasterio.open(reference_path) as reference:
        if reference.crs is None:
            raise ValueError("Reference raster has no CRS.")

        height = reference.height
        width = reference.width
        reference_transform = reference.transform
        reference_crs = reference.crs

        geometry = transform_geom(
            "EPSG:4326",
            reference_crs,
            search_area,
        )

        inside_search_area = geometry_mask(
            [geometry],
            out_shape=(height, width),
            transform=reference_transform,
            invert=True,
        )

        valid_mask = (
            inside_search_area
            & (reference.read_masks(1) > 0)
        )

    # Require valid coverage in every required band.
    for band in FLOOD_BANDS:
        band_path = os.path.join(data_dir, f"{band}.tif")

        if not os.path.exists(band_path):
            raise FileNotFoundError(
                f"Required band not found: {band_path}"
            )

        if band == "B02":
            continue

        with rasterio.open(band_path) as source:
            if source.crs is None:
                raise ValueError(f"{band} raster has no CRS.")

            source_mask = source.read_masks(1)

            aligned_mask = np.zeros(
                (height, width),
                dtype=np.uint8,
            )

            reproject(
                source=source_mask,
                destination=aligned_mask,
                src_transform=source.transform,
                src_crs=source.crs,
                dst_transform=reference_transform,
                dst_crs=reference_crs,
                resampling=Resampling.nearest,
                src_nodata=0,
                dst_nodata=0,
            )

            valid_mask &= aligned_mask > 0

    return valid_mask


def create_evacuation_search_area(
    latitude: float,
    longitude: float,
    radius_m: float = 3000,
) -> dict:
    """
    Create an approximately circular search area around the user.

    Returns a GeoJSON geometry in EPSG:4326.
    Uses a local metric projection to make the radius meaningful.
    """
    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90.")

    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180.")

    if radius_m <= 0:
        raise ValueError("Search radius must be positive.")

    from pyproj import CRS, Transformer
    from shapely.ops import transform

    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={latitude} "
        f"+lon_0={longitude} +datum=WGS84 +units=m +no_defs"
    )

    to_local = Transformer.from_crs(
        "EPSG:4326", local_crs, always_xy=True
    ).transform

    to_wgs84 = Transformer.from_crs(
        local_crs, "EPSG:4326", always_xy=True
    ).transform

    point = transform(to_local, Point(longitude, latitude))
    circle = point.buffer(radius_m)
    circle_wgs84 = transform(to_wgs84, circle)

    return mapping(circle_wgs84)


def find_evacuation_satellite_scene(
    latitude: float,
    longitude: float,
    radius_m: float = 3000,
    start_date: str | None = None,
    end_date: str | None = None,
    max_cloud_cover: float = 20,
) -> dict:
    """
    Find the newest usable Sentinel-2 scene covering the
    evacuation search area.
    """
    if start_date is None:
        start_date = (
            date.today() - timedelta(days=180)
        ).isoformat()

    if end_date is None:
        end_date = date.today().isoformat()

    search_area = create_evacuation_search_area(
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
    )

    scenes = search_satellite_images(
        possible_route_area=search_area,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=max_cloud_cover,
    )

    if not scenes:
        raise ValueError(
            "No suitable Sentinel-2 scene was found "
            "for the evacuation search area."
        )

    return {
        "search_area": search_area,
        "scene": scenes[0],
    }
