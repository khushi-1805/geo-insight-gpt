from __future__ import annotations

import uuid
from pathlib import Path
from datetime import date, timedelta
from typing import Any, Optional

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import reproject, Resampling, transform_geom

from pyproj import CRS, Transformer
from shapely.geometry import Point, mapping
from shapely.ops import transform as shapely_transform

from flood.satellite import (
    FLOOD_BANDS,
    search_satellite_images,
    download_and_clip_bands,
)

from flood.preprocessing import (
    load_flood_bands,
    get_flood_raster_metadata,
)

from flood.flood_detection import detect_flood

from evacuation.dry_area_detector import detect_large_dry_areas
from evacuation.area_measurements import measure_candidate_areas
from evacuation.area_filter import filter_area_candidates
from evacuation.evacuation_service import build_evacuation_response
def create_evacuation_search_area(
    latitude: float,
    longitude: float,
    radius_m: float = 3000,
) -> dict:
    """
    Create a circular search area around the user's location.
    The returned geometry is in EPSG:4326.
    """

    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90")

    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180")

    if radius_m <= 0:
        raise ValueError("Radius must be positive")

    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={latitude} +lon_0={longitude} "
        "+datum=WGS84 +units=m +no_defs"
    )

    forward_transformer = Transformer.from_crs(
        "EPSG:4326",
        local_crs,
        always_xy=True,
    )

    reverse_transformer = Transformer.from_crs(
        local_crs,
        "EPSG:4326",
        always_xy=True,
    )

    center = Point(longitude, latitude)

    projected_center = shapely_transform(
        forward_transformer.transform,
        center,
    )

    projected_buffer = projected_center.buffer(radius_m)

    geographic_buffer = shapely_transform(
        reverse_transformer.transform,
        projected_buffer,
    )

    return mapping(geographic_buffer)


def find_evacuation_satellite_scene(
    latitude: float,
    longitude: float,
    radius_m: float = 3000,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_cloud_cover: float = 20,
) -> dict:
    """
    Find the newest suitable Sentinel-2 scene covering the search area.
    """

    search_area = create_evacuation_search_area(
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
    )

    if end_date is None:
        end_date = date.today().isoformat()

    if start_date is None:
        start_date = (
            date.today() - timedelta(days=180)
        ).isoformat()

    scenes = search_satellite_images(
        possible_route_area=search_area,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=max_cloud_cover,
    )

    if not scenes:
        raise ValueError(
            "No suitable Sentinel-2 imagery found for this location"
        )

    return {
        "search_area": search_area,
        "scene": scenes[0],
    }


def build_valid_pixel_mask(
    data_dir: str,
    search_area: dict,
) -> np.ndarray:
    """
    Build a validity mask using all required Sentinel-2 bands.

    The search area is supplied in EPSG:4326 and is transformed
    into the raster CRS before masking.
    """

    reference_path = Path(data_dir) / "B02.tif"

    if not reference_path.exists():
        raise FileNotFoundError(
            f"Reference band not found: {reference_path}"
        )

    with rasterio.open(reference_path) as reference:
        reference_transform = reference.transform
        reference_crs = reference.crs
        height = reference.height
        width = reference.width

        # Transform WGS84 search geometry into the raster CRS.
        raster_search_area = transform_geom(
            "EPSG:4326",
            reference_crs,
            search_area,
        )

        inside_geometry = geometry_mask(
            [raster_search_area],
            out_shape=(height, width),
            transform=reference_transform,
            invert=True,
        )

        valid_mask = (
            reference.read_masks(1) > 0
        ) & inside_geometry

    for band in FLOOD_BANDS:
        band_path = Path(data_dir) / f"{band}.tif"

        if not band_path.exists():
            raise FileNotFoundError(
                f"Required band not found: {band_path}"
            )

        with rasterio.open(band_path) as source:
            source_mask = source.read_masks(1) > 0

            aligned_mask = np.zeros(
                (height, width),
                dtype=np.uint8,
            )

            reproject(
                source=source_mask.astype(np.uint8),
                destination=aligned_mask,
                src_transform=source.transform,
                src_crs=source.crs,
                dst_transform=reference_transform,
                dst_crs=reference_crs,
                resampling=Resampling.nearest,
            )

            valid_mask &= aligned_mask.astype(bool)

    return valid_mask
def _run_detection_stage(
    latitude: float,
    longitude: float,
    radius_m: float = 3000,
    min_area_m2: float = 10_000,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_cloud_cover: float = 20,
) -> dict:
    """
    Shared satellite detection stage.
    Downloads imagery, builds validity mask and detects dry-looking areas.
    """

    scene_result = find_evacuation_satellite_scene(
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=max_cloud_cover,
    )

    search_area = scene_result["search_area"]
    scene = scene_result["scene"]

    data_dir = str(
        Path("evacuation_data")
        / f"run_{uuid.uuid4().hex[:12]}"
    )

    Path(data_dir).mkdir(
        parents=True,
        exist_ok=True,
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
            "No valid satellite pixels cover the search area"
        )

    image = load_flood_bands(
        data_dir=data_dir,
        normalize=False,
    )

    flood_mask, _mndwi = detect_flood(
        image,
        threshold=0.0,
    )

    metadata = get_flood_raster_metadata(data_dir)

    if flood_mask.shape != valid_mask.shape:
        raise ValueError(
            "Flood mask and validity mask have different shapes"
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
        "scene": scene,
        "search_area": search_area,
        "data_dir": data_dir,
        "valid_mask": valid_mask,
        "flood_mask": flood_mask,
        "metadata": metadata,
        "dry_areas": dry_areas,
        "detected_area_count": len(dry_areas),
        "warnings": [
            "MNDWI thresholding is a water indicator, not a validated flood model.",
            "Detected dry-looking areas are not verified evacuation shelters.",
        ],
    }


def detect_evacuation_dry_areas(
    latitude: float,
    longitude: float,
    radius_m: float = 3000,
    min_area_m2: float = 10_000,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_cloud_cover: float = 20,
) -> dict:
    """
    Detection-only workflow.
    """

    result = _run_detection_stage(
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
        min_area_m2=min_area_m2,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=max_cloud_cover,
    )

    # Compatibility with existing detection API and tests.
    result["candidate_count"] = len(result["dry_areas"])
    result["verification_status"] = "unverified"

    return result
def run_evacuation_analysis(
    latitude: float,
    longitude: float,
    radius_m: float = 3000,
    min_area_m2: float = 10_000,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_cloud_cover: float = 20,
    building_geometries: Optional[list[Any]] = None,
    building_data_complete: bool = False,
    max_building_fraction: Optional[float] = 0.10,
    max_flood_fraction: float = 0.0,
    limit: int = 5,
) -> dict:
    """
    Full evacuation-candidate workflow.

    Building geometries must be WGS84 GeoJSON geometries.

    Set building_data_complete=True only when the supplied footprint
    dataset is known to cover the complete search area.
    """

    detection = _run_detection_stage(
        latitude=latitude,
        longitude=longitude,
        radius_m=radius_m,
        min_area_m2=min_area_m2,
        start_date=start_date,
        end_date=end_date,
        max_cloud_cover=max_cloud_cover,
    )

    scene = detection["scene"]
    dry_areas = detection["dry_areas"]
    valid_mask = detection["valid_mask"]
    flood_mask = detection["flood_mask"]
    metadata = detection["metadata"]

    # Only polygons can be used for spatial measurements.
    measurable_areas = [
        area
        for area in dry_areas
        if area.geometry is not None
    ]

    # Calculate flood and building measurements.
    measurements = measure_candidate_areas(
        areas=measurable_areas,
        flood_mask=flood_mask,
        valid_mask=valid_mask,
        raster_transform=metadata["transform"],
        raster_crs=metadata["crs"],
        building_geometries=building_geometries,
        building_data_complete=building_data_complete,
    )

    # Filter candidates using the measurements.
    candidates = filter_area_candidates(
        areas=measurable_areas,
        measurements=measurements,
        min_area_m2=min_area_m2,
        max_flood_fraction=max_flood_fraction,
        max_building_fraction=max_building_fraction,
    )

    # Rank eligible candidates and create the response.
    response = build_evacuation_response(
        user_lat=latitude,
        user_lon=longitude,
        candidates=candidates,
        flood_data_timestamp=str(scene.get("date")),
        model_name="Sentinel-2 L2A + MNDWI threshold",
        limit=limit,
    )

    warnings = detection["warnings"] + [
        "A polygon extracted from dry pixels is not independently proven flood-safe.",
        "Building coverage is only as complete as the supplied footprint dataset.",
        "Straight-line distance is not the same as accessible road distance.",
    ]
    candidate_summaries = []

    for candidate in candidates[:20]:
        area = candidate.area

        candidate_summaries.append({
            "area_m2": float(area.area_m2),
            "latitude": float(area.center_lat),
            "longitude": float(area.center_lon),
            "pixel_count": int(area.pixel_count),
            "flood_fraction": float(candidate.flood_fraction),
            "building_fraction": (
                float(candidate.building_fraction)
                if candidate.building_fraction is not None
                else None
            ),
            "eligible": bool(candidate.eligible),
            "reasons": list(candidate.reasons or []),
            "warnings": list(getattr(candidate, "warnings", []) or []),
        })

    return {
        "success": True,
        "scene": {
            "image_id": scene.get("id"),
            "date": scene.get("date"),
            "cloud_cover": scene.get("cloud_cover"),
        },
        "search_radius_m": radius_m,
        "valid_pixel_count": int(valid_mask.sum()),
        "detected_area_count": len(dry_areas),
        "measurable_area_count": len(measurable_areas),
        "candidate_count": len(candidates),
        "candidate_summaries": candidate_summaries,
        "eligible_area_count": sum(
            1 for candidate in candidates
            if candidate.eligible
        ),
        "response": response,
        "verification_status": "unverified",
        "warnings": warnings,
        "data_dir": detection["data_dir"],
    }