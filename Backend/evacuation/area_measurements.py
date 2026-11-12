"""Spatial measurements for detected dry-area candidates.

Building geometries supplied to this module must be GeoJSON-like geometries
in EPSG:4326. An empty list means zero mapped buildings ONLY when the caller
knows the building dataset/query is complete for the full search area.
Pass None when building data is unavailable or incomplete.
"""
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import shape
from shapely.ops import transform as shapely_transform, unary_union
from pyproj import Transformer

from evacuation.dry_area_detector import DryArea


@dataclass
class AreaMeasurements:
    flood_fraction: Optional[float]
    building_fraction: Optional[float]
    measurements_valid: bool
    warnings: list[str] = field(default_factory=list)


def _to_shapely_geometry(geometry: Any):
    if geometry is None:
        raise ValueError("Candidate has no polygon geometry")
    if hasattr(geometry, "geom_type"):
        return geometry
    return shape(geometry)


def measure_one_area(
    area: DryArea,
    flood_mask: np.ndarray,
    valid_mask: np.ndarray,
    raster_transform,
    raster_crs,
    building_geometries: Optional[Sequence[Any]] = None,
    building_data_complete: bool = False,
) -> AreaMeasurements:
    """Measure flood-mask overlap and mapped building-footprint coverage."""
    warnings: list[str] = []
    flood_mask = np.asarray(flood_mask, dtype=bool)
    valid_mask = np.asarray(valid_mask, dtype=bool)

    if flood_mask.ndim != 2 or valid_mask.ndim != 2:
        raise ValueError("Masks must be 2D arrays")
    if flood_mask.shape != valid_mask.shape:
        raise ValueError("flood_mask and valid_mask shapes must match")
    if raster_crs is None or not raster_crs.is_projected:
        raise ValueError("A projected raster CRS is required for area measurement")
    if raster_crs.linear_units not in ("metre", "meter", "metres", "meters"):
        raise ValueError("Raster CRS must use metres")

    polygon = _to_shapely_geometry(area.geometry)
    polygon_raster_crs = shapely_transform(
        Transformer.from_crs(
            "EPSG:4326", raster_crs, always_xy=True
        ).transform,
        polygon,
    )

    inside = geometry_mask(
        [polygon_raster_crs.__geo_interface__],
        out_shape=flood_mask.shape,
        transform=raster_transform,
        invert=True,
        all_touched=False,
    )
    measured_pixels = inside & valid_mask
    valid_count = int(measured_pixels.sum())

    flood_fraction: Optional[float]
    if valid_count == 0:
        flood_fraction = None
        warnings.append("No valid raster pixels overlap this candidate polygon.")
    else:
        flood_fraction = float(
            (flood_mask & measured_pixels).sum() / valid_count
        )
        # The polygon was generated from dry pixels. A non-zero overlap is
        # a consistency warning, not independent confirmation of safety.
        if flood_fraction > 0:
            warnings.append(
                "Flood-mask overlap found inside a polygon generated from dry pixels; inspect raster alignment."
            )
        else:
            warnings.append(
                "Flood fraction is a consistency check because this polygon was extracted from the dry mask."
            )

    building_fraction: Optional[float] = None
    if building_geometries is None or not building_data_complete:
        warnings.append(
            "Building coverage is unknown because complete building-footprint data was not supplied."
        )
    else:
        if polygon_raster_crs.is_empty or polygon_raster_crs.area <= 0:
            warnings.append("Candidate polygon has invalid or zero area.")
        else:
            building_shapes = []
            for item in building_geometries:
                if item is None:
                    continue
                geom = _to_shapely_geometry(item)
                if not geom.is_empty:
                    projected = shapely_transform(
                        Transformer.from_crs(
                            "EPSG:4326", raster_crs, always_xy=True
                        ).transform,
                        geom,
                    )
                    if projected.is_valid:
                        building_shapes.append(projected)
                    else:
                        building_shapes.append(projected.buffer(0))

            if building_shapes:
                buildings_union = unary_union(building_shapes)
                covered_area = polygon_raster_crs.intersection(
                    buildings_union
                ).area
            else:
                # A complete, successful query returned no building features.
                covered_area = 0.0

            building_fraction = float(
                min(1.0, max(0.0, covered_area / polygon_raster_crs.area))
            )

    measurements_valid = (
        flood_fraction is not None
        and building_fraction is not None
    )
    return AreaMeasurements(
        flood_fraction=flood_fraction,
        building_fraction=building_fraction,
        measurements_valid=measurements_valid,
        warnings=warnings,
    )


def measure_candidate_areas(
    areas: Sequence[DryArea],
    flood_mask: np.ndarray,
    valid_mask: np.ndarray,
    raster_transform,
    raster_crs,
    building_geometries: Optional[Sequence[Any]] = None,
    building_data_complete: bool = False,
) -> list[AreaMeasurements]:
    """Return one measurement record per area, preserving input order."""
    return [
        measure_one_area(
            area=area,
            flood_mask=flood_mask,
            valid_mask=valid_mask,
            raster_transform=raster_transform,
            raster_crs=raster_crs,
            building_geometries=building_geometries,
            building_data_complete=building_data_complete,
        )
        for area in areas
    ]
