from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from rasterio.crs import CRS
from rasterio.features import shapes
from rasterio.warp import transform as transform_coords, transform_geom
from scipy import ndimage


@dataclass
class DryArea:
    area_m2: float
    center_lat: float
    center_lon: float
    pixel_count: int
    geometry: Optional[dict[str, Any]] = None


def detect_large_dry_areas(
    flood_mask: np.ndarray,
    transform,
    crs: CRS,
    min_area_m2: float = 10_000,
    connectivity: int = 8,
    valid_mask: Optional[np.ndarray] = None,
) -> list[DryArea]:
    """Extract connected, valid, non-water regions as WGS84 polygons."""
    flood_mask = np.asarray(flood_mask, dtype=bool)

    if flood_mask.ndim != 2:
        raise ValueError("flood_mask must be a 2D array")
    if connectivity not in (4, 8):
        raise ValueError("connectivity must be 4 or 8")
    if min_area_m2 <= 0:
        raise ValueError("min_area_m2 must be positive")
    if crs is None or not crs.is_projected:
        raise ValueError("A projected CRS is required")
    if crs.linear_units not in ("metre", "meter", "metres", "meters"):
        raise ValueError("Raster CRS must use metres")

    if valid_mask is None:
        valid = np.ones(flood_mask.shape, dtype=bool)
    else:
        valid = np.asarray(valid_mask, dtype=bool)
        if valid.shape != flood_mask.shape:
            raise ValueError("valid_mask shape must match flood_mask")

    dry = (~flood_mask) & valid
    structure = ndimage.generate_binary_structure(
        2, 1 if connectivity == 4 else 2
    )
    labels, count = ndimage.label(dry, structure=structure)

    pixel_area_m2 = abs(
        transform.a * transform.e - transform.b * transform.d
    )
    if pixel_area_m2 <= 0:
        raise ValueError("Invalid raster transform")

    results: list[DryArea] = []

    for label_id in range(1, count + 1):
        component_mask = labels == label_id
        rows, cols = np.where(component_mask)
        pixel_count = int(len(rows))
        area_m2 = pixel_count * pixel_area_m2

        if area_m2 < min_area_m2:
            continue

        # Polygonize the exact connected component. There should be one
        # connected component, but retain all pieces if polygonization splits it.
        component_shapes = list(
            shapes(
                component_mask.astype(np.uint8),
                mask=component_mask,
                transform=transform,
                connectivity=connectivity,
            )
        )
        if not component_shapes:
            continue

        if len(component_shapes) == 1:
            component_geometry = component_shapes[0][0]
        else:
            from shapely.geometry import shape, mapping
            from shapely.ops import unary_union
            component_geometry = mapping(
                unary_union([shape(item[0]) for item in component_shapes])
            )

        geometry_wgs84 = transform_geom(
            crs, "EPSG:4326", component_geometry
        )

        # Use the mean pixel centre as a representative point.
        center_row = float(rows.mean())
        center_col = float(cols.mean())
        x = (
            transform.c
            + (center_col + 0.5) * transform.a
            + (center_row + 0.5) * transform.b
        )
        y = (
            transform.f
            + (center_col + 0.5) * transform.d
            + (center_row + 0.5) * transform.e
        )
        lon, lat = transform_coords(crs, "EPSG:4326", [x], [y])

        results.append(
            DryArea(
                area_m2=float(area_m2),
                center_lat=float(lat[0]),
                center_lon=float(lon[0]),
                pixel_count=pixel_count,
                geometry=geometry_wgs84,
            )
        )

    return sorted(results, key=lambda item: item.area_m2, reverse=True)
