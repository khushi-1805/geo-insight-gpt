
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from rasterio.crs import CRS
from rasterio.warp import transform as transform_coords
from scipy import ndimage

from typing import Any, Optional

from rasterio.features import shapes
from rasterio.warp import transform_geom



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
) -> List[DryArea]:
    """
    Detect connected dry regions while excluding unknown pixels.

    flood_mask:
        True = flooded, False = dry.

    valid_mask:
        True = valid observation, False = unknown/invalid.
        If omitted, all pixels are assumed valid. Only omit it
        when every pixel in flood_mask is known to be valid.

    Area calculation requires a projected CRS in metres.
    """
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

    # Only valid pixels classified as dry are candidates.
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

    results = []

    for label_id in range(1, count + 1):
        rows, cols = np.where(labels == label_id)
        pixel_count = len(rows)
        area_m2 = pixel_count * pixel_area_m2

        if area_m2 < min_area_m2:
            continue

# Generate polygon geometry for this connected dry area.
        component_mask = labels == label_id

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

        component_geometry = component_shapes[0][0]

        # Convert polygon from raster CRS to WGS84.
        geometry_wgs84 = transform_geom(
            crs,
            "EPSG:4326",
            component_geometry,
        )

# Use the mean pixel position as a representative point.
        center_row = float(rows.mean())

        # Use the mean pixel position as a representative point.
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

        lon, lat = transform_coords(
            crs, "EPSG:4326", [x], [y]
        )

        results.append(
    DryArea(
        area_m2=area_m2,
        center_lat=lat[0],
        center_lon=lon[0],
        pixel_count=pixel_count,
        geometry=geometry_wgs84,
    )
)

    return sorted(results, key=lambda area: area.area_m2, reverse=True)
