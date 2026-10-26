import numpy as np
from shapely.geometry import LineString
from pyproj import Transformer


MIN_ROUTE_COVERAGE_PERCENT = 80.0
SAMPLE_DISTANCE_METERS = 10.0


def calculate_route_risk(
    route_coordinates,
    flood_mask,
    transform,
    crs,
):
    """Estimate route flood overlap; return unknown if raster coverage is insufficient."""
    if len(route_coordinates) < 2:
        raise ValueError("Route must contain at least 2 points")

    transformer = Transformer.from_crs(
        "EPSG:4326", crs, always_xy=True
    )
    projected_points = [
        transformer.transform(lon, lat)
        for lon, lat in route_coordinates
    ]
    route = LineString(projected_points)
    total_length = route.length

    if total_length <= 0:
        return {
            "route_length_m": 0.0,
            "flooded_length_m": 0.0,
            "flooded_percentage": 0.0,
            "coverage_percentage": 0.0,
            "risk": "unknown",
        }

    distances = np.arange(0, total_length, SAMPLE_DISTANCE_METERS)
    if len(distances) == 0:
        distances = np.array([0.0])

    height, width = flood_mask.shape
    valid_samples = 0
    flooded_samples = 0

    for distance in distances:
        point = route.interpolate(float(distance))
        col, row = ~transform * (point.x, point.y)
        row, col = int(row), int(col)

        if 0 <= row < height and 0 <= col < width:
            valid_samples += 1
            if flood_mask[row, col] == 1:
                flooded_samples += 1

    coverage_percentage = (valid_samples / len(distances)) * 100.0

    # A route with little raster overlap must not be reported as low-risk.
    if (
        valid_samples == 0
        or coverage_percentage < MIN_ROUTE_COVERAGE_PERCENT
    ):
        return {
            "route_length_m": round(total_length, 2),
            "flooded_length_m": None,
            "flooded_percentage": None,
            "coverage_percentage": round(coverage_percentage, 2),
            "risk": "unknown",
        }

    flooded_percentage = (flooded_samples / valid_samples) * 100.0
    flooded_length = flooded_samples * SAMPLE_DISTANCE_METERS

    if flooded_percentage >= 30:
        risk = "high"
    elif flooded_percentage >= 10:
        risk = "medium"
    else:
        risk = "low"

    return {
        "route_length_m": round(total_length, 2),
        "flooded_length_m": round(flooded_length, 2),
        "flooded_percentage": round(flooded_percentage, 2),
        "coverage_percentage": round(coverage_percentage, 2),
        "risk": risk,
    }
