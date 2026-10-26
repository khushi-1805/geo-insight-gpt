from shapely.geometry import shape, mapping
from shapely.ops import transform, unary_union
from pyproj import Transformer


CORRIDOR_BUFFER_METERS = 500


def create_route_corridor(routes):
    """
    Create one buffered polygon around all candidate routes.

    routes:
        List of route dictionaries containing GeoJSON LineString paths.

    Returns:
        GeoJSON Polygon representing the possible route area.
    """

    if not routes:
        raise ValueError("No routes provided.")

    route_geometries = []

    for route in routes:
        path = route.get("path")

        if not path:
            continue

        geometry = shape(path)

        if geometry.geom_type != "LineString":
            continue

        route_geometries.append(geometry)

    if not route_geometries:
        raise ValueError("No valid route geometries found.")

    # Combine all candidate routes
    combined_routes = unary_union(route_geometries)

    # Use the route centroid to determine the local UTM zone
    centroid = combined_routes.centroid

    longitude = centroid.x
    latitude = centroid.y

    utm_zone = int((longitude + 180) / 6) + 1

    if latitude >= 0:
        utm_epsg = 32600 + utm_zone
    else:
        utm_epsg = 32700 + utm_zone

    # WGS84 -> local UTM
    to_utm = Transformer.from_crs(
        "EPSG:4326",
        f"EPSG:{utm_epsg}",
        always_xy=True,
    ).transform

    # UTM -> WGS84
    to_wgs84 = Transformer.from_crs(
        f"EPSG:{utm_epsg}",
        "EPSG:4326",
        always_xy=True,
    ).transform

    # Project to meters
    projected_routes = transform(to_utm, combined_routes)

    # Buffer by 500 meters
    buffered = projected_routes.buffer(CORRIDOR_BUFFER_METERS)

    # Convert back to latitude/longitude
    corridor = transform(to_wgs84, buffered)

    return mapping(corridor)