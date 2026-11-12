
"""Flood escape-point detection built on the existing evacuation pipeline.

This module reuses the existing satellite/detection stage. It does not alter
flood routing, satellite acquisition, MNDWI, SCL, or preprocessing modules.

It generates candidate points beyond the detected water boundary and validates
them against the complete detected water geometry and raster water mask.

Candidates are not confirmed safe destinations. Road-network routing and
real-world shelter verification are not performed here.
"""

from __future__ import annotations
from typing import Any

import numpy as np
from pyproj import CRS, Transformer
from rasterio.features import shapes
from rasterio.transform import rowcol
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import (
    nearest_points,
    transform as shapely_transform,
    unary_union,
)

from evacuation.pipeline import _run_detection_stage


def _polygonize_water(
    flood_mask: np.ndarray,
    valid_mask: np.ndarray,
    raster_transform,
):
    """Dissolve valid water-classified pixels into a water polygon."""

    flood_mask = np.asarray(flood_mask, dtype=bool)
    valid_mask = np.asarray(valid_mask, dtype=bool)

    if flood_mask.ndim != 2:
        raise ValueError("flood_mask must be a 2D array")

    if flood_mask.shape != valid_mask.shape:
        raise ValueError(
            "flood_mask and valid_mask must have identical shapes"
        )

    water = flood_mask & valid_mask

    if not water.any():
        raise ValueError("No valid water-classified pixels were detected")

    polygons = [
        shape(geometry)
        for geometry, value in shapes(
            water.astype(np.uint8),
            mask=water,
            transform=raster_transform,
            connectivity=8,
        )
        if value == 1
    ]

    if not polygons:
        raise ValueError("Could not polygonize the detected water pixels")

    water_geometry = unary_union(polygons)

    if water_geometry.is_empty:
        raise ValueError("The detected water polygon is empty")

    return water_geometry


def _is_known_dry_segment(
    boundary_point_local: Point,
    target_point_local: Point,
    *,
    local_to_raster: Transformer,
    raster_transform,
    flood_mask: np.ndarray,
    valid_mask: np.ndarray,
    sample_step_m: float = 10.0,
    ignore_boundary_m: float = 20.0,
) -> bool:
    """
    Require sampled raster pixels between the boundary and target
    to be valid and classified as dry.
    """

    segment = LineString(
        [boundary_point_local, target_point_local]
    )

    length_m = segment.length

    if length_m <= ignore_boundary_m:
        return False

    sample_count = max(
        2,
        int(np.ceil(length_m / sample_step_m)),
    )

    distances = np.linspace(
        ignore_boundary_m,
        length_m,
        sample_count,
    )

    for distance in distances:
        point = segment.interpolate(float(distance))

        raster_x, raster_y = local_to_raster.transform(
            point.x,
            point.y,
        )

        row, col = rowcol(
            raster_transform,
            raster_x,
            raster_y,
        )

        if not (
            0 <= row < valid_mask.shape[0]
            and 0 <= col < valid_mask.shape[1]
        ):
            return False

        if not valid_mask[row, col]:
            return False

        if flood_mask[row, col]:
            return False

    return True


def _make_exit_candidates(
    water_geometry_local,
    user_point_local: Point,
    *,
    local_crs: CRS,
    raster_crs: Any,
    raster_transform,
    flood_mask: np.ndarray,
    valid_mask: np.ndarray,
    safety_offset_m: float,
    max_candidates: int,
):
    """
    Generate candidate points beyond the containing water polygon.

    Every candidate is checked against the complete water geometry,
    a 20-metre safety buffer, and the raster dry-pixel mask.
    """

    components = (
        list(water_geometry_local.geoms)
        if water_geometry_local.geom_type == "MultiPolygon"
        else [water_geometry_local]
    )

    containing = [
        component
        for component in components
        if component.covers(user_point_local)
    ]

    if not containing:
        raise ValueError(
            "The supplied user location is not inside the detected "
            "water polygon. Check the GPS location, imagery date, "
            "and water classification."
        )

    flood_polygon = min(
        containing,
        key=lambda polygon: polygon.boundary.distance(
            user_point_local
        ),
    )

    exterior = LineString(flood_polygon.exterior.coords)

    if exterior.length <= 0:
        raise ValueError(
            "The detected flood boundary has no measurable length"
        )

    nearest_boundary_point = nearest_points(
        user_point_local,
        exterior,
    )[1]

    nearest_distance_along = exterior.project(
        nearest_boundary_point
    )

    perimeter = exterior.length

    # Sample the boundary at regular intervals.
    spacing = max(20.0, perimeter / 300.0)

    positions = list(
        np.arange(0.0, perimeter, spacing)
    )

    positions.sort(
        key=lambda value: min(
            (value - nearest_distance_along) % perimeter,
            (nearest_distance_along - value) % perimeter,
        )
    )

    # Coordinate transformers.
    local_to_raster = Transformer.from_crs(
        local_crs,
        raster_crs,
        always_xy=True,
    )

    local_to_wgs84 = Transformer.from_crs(
        local_crs,
        "EPSG:4326",
        always_xy=True,
    )

    wgs84_to_local = Transformer.from_crs(
        "EPSG:4326",
        local_crs,
        always_xy=True,
    )

    # Calculate this once, not once per candidate.
    water_safety_buffer = water_geometry_local.buffer(20.0)

    interior_reference = flood_polygon.representative_point()

    candidates = []
    seen = set()

    for distance_along in positions:

        boundary_point = exterior.interpolate(
            float(distance_along)
        )

        # Determine the outward direction.
        dx = boundary_point.x - interior_reference.x
        dy = boundary_point.y - interior_reference.y

        magnitude = float(np.hypot(dx, dy))

        if magnitude == 0:
            continue

        ux = dx / magnitude
        uy = dy / magnitude

        # Generate a point beyond the boundary.
        target = Point(
            boundary_point.x + ux * safety_offset_m,
            boundary_point.y + uy * safety_offset_m,
        )

        # Check against the complete water extent,
        # not just the polygon containing the user.
        if water_safety_buffer.covers(target):
            continue

        # Check the raster pixels between boundary and candidate.
        if not _is_known_dry_segment(
            boundary_point,
            target,
            local_to_raster=local_to_raster,
            raster_transform=raster_transform,
            flood_mask=flood_mask,
            valid_mask=valid_mask,
        ):
            continue

        # Convert candidate into geographic coordinates.
        lon, lat = local_to_wgs84.transform(
            target.x,
            target.y,
        )

        # Convert the returned coordinates back into local CRS.
        check_x, check_y = wgs84_to_local.transform(
            lon,
            lat,
        )

        check_point = Point(check_x, check_y)
        # Validate the exact candidate pixel in the original raster.
        raster_x, raster_y = local_to_raster.transform(
            check_point.x,
            check_point.y,
        )

        row, col = rowcol(
            raster_transform,
            raster_x,
            raster_y,
        )

        # Reject candidates outside the raster.
        if not (
            0 <= row < valid_mask.shape[0]
            and 0 <= col < valid_mask.shape[1]
        ):
            print("REJECTED: Outside raster")
            continue

        # Reject invalid or water-classified pixels.
        if not valid_mask[row, col]:
            print("REJECTED: Invalid satellite pixel")
            continue

        if flood_mask[row, col]:
            print("REJECTED: Candidate pixel is classified as water")
            continue
        # Final validation against the entire water geometry.
        inside_water = water_geometry_local.covers(
            check_point
        )

        water_distance = water_geometry_local.distance(
            check_point
        )

        print("\n--- FINAL CANDIDATE VALIDATION ---")
        print("Latitude:", lat)
        print("Longitude:", lon)
        print("Inside water:", inside_water)
        print(
            "Distance from water:",
            water_distance,
            "metres",
        )

        # Reject points inside water or within the safety buffer.
        if inside_water or water_distance < 20.0:
            print("REJECTED: Candidate failed water validation")
            continue

        print("FINAL ACCEPTED:", lat, lon)

        key = (
            round(lat, 6),
            round(lon, 6),
        )

        if key in seen:
            continue

        seen.add(key)

        candidates.append(
            {
                "latitude": float(lat),
                "longitude": float(lon),
                "distance_from_user_m": float(
                    user_point_local.distance(check_point)
                ),
                "safety_offset_m": float(safety_offset_m),
                "verification_status": (
                    "satellite_mask_checked_unverified"
                ),
                "warnings": [
                    (
                        "Target is outside the complete detected "
                        "water extent and beyond the configured buffer."
                    ),
                    (
                        "Satellite classification does not prove "
                        "future flood safety."
                    ),
                    "Road accessibility has not yet been checked.",
                ],
            }
        )

    candidates.sort(
        key=lambda item: item["distance_from_user_m"]
    )

    return candidates[:max_candidates], flood_polygon


def run_flood_escape_analysis(
    latitude: float,
    longitude: float,
    *,
    radius_m: float = 3000,
    safety_offset_m: float = 500,
    start_date: str | None = None,
    end_date: str | None = None,
    max_cloud_cover: float = 20,
    max_candidates: int = 5,
) -> dict:
    """
    Run existing satellite detection and find candidate dry-side exit points.

    The user must be inside the detected water polygon.
    Candidates are ranked by straight-line distance.
    Road routing and real-world safety are not verified.
    """

    if not -90 <= latitude <= 90:
        raise ValueError(
            "Latitude must be between -90 and 90"
        )

    if not -180 <= longitude <= 180:
        raise ValueError(
            "Longitude must be between -180 and 180"
        )

    if radius_m <= 0:
        raise ValueError("radius_m must be positive")

    if safety_offset_m <= 0:
        raise ValueError("safety_offset_m must be positive")

    if max_candidates < 1:
        raise ValueError(
            "max_candidates must be at least 1"
        )

    # Reuse the existing detection pipeline.
    detection = _run_detection_stage(
    latitude=latitude,
    longitude=longitude,
    radius_m=radius_m,
    start_date=start_date,
    end_date=end_date,
    max_cloud_cover=max_cloud_cover,
)

    flood_mask = np.asarray(
        detection["flood_mask"],
        dtype=bool,
    )

    valid_mask = np.asarray(
        detection["valid_mask"],
        dtype=bool,
    )

    metadata = detection["metadata"]

    raster_crs = CRS.from_user_input(
        metadata["crs"]
    )

    if not raster_crs.is_projected:
        raise ValueError(
            "The flood raster must use a projected CRS"
        )

    water_geometry = _polygonize_water(
        flood_mask,
        valid_mask,
        metadata["transform"],
    )

    # Local azimuthal-equidistant projection.
    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={latitude} +lon_0={longitude} "
        "+datum=WGS84 +units=m +no_defs"
    )

    raster_to_wgs84 = Transformer.from_crs(
        raster_crs,
        "EPSG:4326",
        always_xy=True,
    )

    wgs84_to_local = Transformer.from_crs(
        "EPSG:4326",
        local_crs,
        always_xy=True,
    )

    local_to_wgs84 = Transformer.from_crs(
        local_crs,
        "EPSG:4326",
        always_xy=True,
    )

    # Transform water geometry into local metric coordinates.
    water_wgs84 = shapely_transform(
        raster_to_wgs84.transform,
        water_geometry,
    )

    water_local = shapely_transform(
        wgs84_to_local.transform,
        water_wgs84,
    )

    user_local = Point(
        *wgs84_to_local.transform(
            longitude,
            latitude,
        )
    )

    scene = detection.get("scene", {})

    # Return water geometry even if the submitted location is outside it.
    if not water_local.covers(user_local):

        boundary_wgs84 = shapely_transform(
            local_to_wgs84.transform,
            water_local.boundary,
        )

        return {
            "success": True,
            "user_location": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "user_inside_detected_water": False,
            "water_extent": mapping(water_wgs84),
            "flood_boundary": mapping(boundary_wgs84),
            "safety_offset_m": float(safety_offset_m),
            "candidate_count": 0,
            "candidates": [],
            "scene": {
                "image_id": scene.get("id"),
                "date": scene.get("date"),
                "cloud_cover": scene.get("cloud_cover"),
            },
            "data_dir": detection.get("data_dir"),
            "message": (
                "The submitted location is outside the detected "
                "water extent. The water classification is shown "
                "for inspection; no escape candidates were generated."
            ),
            "verification_status": "unverified",
            "warnings": [
                (
                    "The detected water extent is based on the "
"Sentinel-2 MNDWI thresholding."
                ),
                (
                    "Permanent rivers/lakes may be included; "
                    "this is not yet a before/after flood-change map."
                ),
                (
                    "The submitted point may not represent "
                    "the affected person's exact location."
                ),
                "Water classification is not proof of an active flood.",
            ],
        }

    # Generate and validate candidate points.
    candidates, containing_flood_polygon = _make_exit_candidates(
        water_local,
        user_local,
        local_crs=local_crs,
        raster_crs=raster_crs,
        raster_transform=metadata["transform"],
        flood_mask=flood_mask,
        valid_mask=valid_mask,
        safety_offset_m=safety_offset_m,
        max_candidates=max_candidates,
    )

    if not candidates:
        message = (
            "The user is inside the detected water area, but no "
            "candidate could be verified as valid and non-water "
            "at the configured offset."
        )
    else:
        message = (
            "Candidate dry-side exit points found and ranked by "
            "straight-line distance. Road accessibility and "
            "real-world safety are not verified."
        )

    boundary_wgs84 = shapely_transform(
        local_to_wgs84.transform,
        containing_flood_polygon.boundary,
    )

    return {
        "success": True,
        "user_location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "user_inside_detected_water": True,
        "water_extent": mapping(water_wgs84),
        "flood_boundary": mapping(boundary_wgs84),
        "safety_offset_m": float(safety_offset_m),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "scene": {
            "image_id": scene.get("id"),
            "date": scene.get("date"),
            "cloud_cover": scene.get("cloud_cover"),
        },
        "data_dir": detection.get("data_dir"),
        "message": message,
        "verification_status": "unverified",
        "warnings": [
            (
                "The detected water extent is based on the "
                "selected Sentinel-2 scene and MNDWI threshold."
            ),
            (
                "Permanent rivers/lakes may be included; "
                "this is not yet a before/after flood-change map."
            ),
            (
                "A dry-looking target may become flooded "
                "after the image acquisition time."
            ),
            (
                "The 500 m offset is a configurable buffer, "
                "not a guarantee of safety."
            ),
            "No road-network route has been calculated in this module yet.",
        ],
    }
