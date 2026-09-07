"""
Water-body analysis using Sentinel-2 imagery from Microsoft
Planetary Computer.

Method:
    MNDWI = (Green - SWIR) / (Green + SWIR)

Water pixels:
    MNDWI > 0

The analysis is restricted to the exact Polygon/MultiPolygon
returned by location.py.

Performance optimization:
    Candidate Sentinel-2 scenes are first checked for whether
    their footprint intersects the actual AOI. Scenes that do
    not sufficiently cover the AOI are deprioritized before
    expensive raster reads.

IMPORTANT:
    The actual water-analysis logic is unchanged.
"""

import sys
import time
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parent.parent)
)

import numpy as np
import pystac_client
import planetary_computer
import rasterio

from rasterio.features import geometry_mask, bounds
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds, transform_geom
from rasterio.enums import Resampling


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

STAC_URL = (
    "https://planetarycomputer.microsoft.com/api/stac/v1"
)

COLLECTION = "sentinel-2-l2a"


# ---------------------------------------------------------------------
# Reusable Planetary Computer catalog
# ---------------------------------------------------------------------

_catalog = None


def get_catalog():

    global _catalog

    if _catalog is None:

        print(
            "\nConnecting to Microsoft Planetary Computer..."
        )

        _catalog = pystac_client.Client.open(
            STAC_URL,
            modifier=planetary_computer.sign_inplace
        )

        print(
            "Planetary Computer connection ready."
        )

    return _catalog


# ---------------------------------------------------------------------
# Satellite search configuration
# ---------------------------------------------------------------------

SEARCH_BUFFER_DEG = 0.02

MAX_SCENE_CLOUD_COVER = 20

MIN_VALID_PIXEL_FRACTION = 0.5

WATER_MNDWI_THRESHOLD = 0.0

SENTINEL2_SCALE = 10000.0


# ---------------------------------------------------------------------
# Fixed seasonal window
# ---------------------------------------------------------------------

SEASON_START_MONTH = 1
SEASON_END_MONTH = 3


# ---------------------------------------------------------------------
# Sentinel-2 SCL values to exclude
# ---------------------------------------------------------------------

SCL_EXCLUDE_VALUES = {
    0,   # No data
    1,   # Saturated / defective
    3,   # Cloud shadow
    8,   # Cloud medium probability
    9,   # Cloud high probability
    10,  # Thin cirrus
    11   # Snow / ice
}


# ---------------------------------------------------------------------
# MNDWI
# ---------------------------------------------------------------------

def calculate_mndwi(
    green,
    swir
):

    denominator = green + swir

    return np.divide(
        green - swir,
        denominator,
        out=np.full_like(
            denominator,
            np.nan,
            dtype=float
        ),
        where=denominator != 0
    )


# ---------------------------------------------------------------------
# Scene footprint / AOI compatibility
# ---------------------------------------------------------------------

def _scene_intersects_aoi(
    image,
    geometry
):
    """
    Check whether the Sentinel-2 scene footprint intersects
    the requested AOI.

    This is only a pre-filter.

    The existing 50% valid-pixel test remains the final
    validation after raster data is actually read.
    """

    try:

        scene_geometry = image.geometry

        if scene_geometry is None:
            return False

        aoi_raster_geometry = geometry

        # Use Shapely if available through the STAC geometry.
        from shapely.geometry import shape

        scene_shape = shape(
            scene_geometry
        )

        aoi_shape = shape(
            aoi_raster_geometry
        )

        return scene_shape.intersects(
            aoi_shape
        )

    except Exception:

        # If footprint checking fails for any reason,
        # do NOT reject the scene.
        #
        # The existing valid-pixel check will still
        # determine whether the scene is usable.
        return True


# ---------------------------------------------------------------------
# Calculate approximate scene/AOI overlap
# ---------------------------------------------------------------------

def _scene_overlap_ratio(
    image,
    geometry
):
    """
    Estimate how much of the AOI is covered by the
    Sentinel-2 scene footprint.

    This value is used ONLY to prioritize candidates.

    It does not replace the existing valid-pixel check.
    """

    try:

        from shapely.geometry import shape

        scene_geometry = image.geometry

        if scene_geometry is None:
            return 0.0

        scene_shape = shape(
            scene_geometry
        )

        aoi_shape = shape(
            geometry
        )

        if not scene_shape.intersects(
            aoi_shape
        ):
            return 0.0

        intersection = (
            scene_shape.intersection(
                aoi_shape
            )
        )

        if aoi_shape.area == 0:
            return 0.0

        ratio = (
            intersection.area
            /
            aoi_shape.area
        )

        return float(
            max(
                0.0,
                min(
                    1.0,
                    ratio
                )
            )
        )

    except Exception:

        # If overlap calculation fails,
        # keep the scene eligible.
        return 1.0


# ---------------------------------------------------------------------
# Sentinel-2 scene search
# ---------------------------------------------------------------------

def get_candidate_sentinel_images(
    geometry,
    year,
    season_start_month=SEASON_START_MONTH,
    season_end_month=SEASON_END_MONTH
):

    search_start_time = time.perf_counter()

    catalog = get_catalog()

    # -------------------------------------------------------------
    # Exact AOI bounding box
    # -------------------------------------------------------------

    left, bottom, right, top = bounds(
        geometry
    )

    bbox = [
        left - SEARCH_BUFFER_DEG,
        bottom - SEARCH_BUFFER_DEG,
        right + SEARCH_BUFFER_DEG,
        top + SEARCH_BUFFER_DEG
    ]

    # -------------------------------------------------------------
    # Seasonal window
    # -------------------------------------------------------------

    start_date = (
        f"{year}-"
        f"{season_start_month:02d}-01"
    )

    if season_end_month == 12:

        end_date = (
            f"{year + 1}-01-01"
        )

    else:

        end_date = (
            f"{year}-"
            f"{season_end_month + 1:02d}-01"
        )

    print(
        f"\nSearching Sentinel-2 scenes for {year}..."
    )

    print(
        f"Search period: "
        f"{start_date} → {end_date}"
    )

    print(
        f"Cloud cover limit: "
        f"{MAX_SCENE_CLOUD_COVER}%"
    )

    search = catalog.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=f"{start_date}/{end_date}",
        query={
            "eo:cloud_cover": {
                "lt": MAX_SCENE_CLOUD_COVER
            }
        }
    )

    print(
        "Fetching candidate scenes..."
    )

    items = list(
        search.items()
    )

    search_elapsed = (
        time.perf_counter()
        - search_start_time
    )

    print(
        f"Scene search completed in "
        f"{search_elapsed:.2f}s"
    )

    if not items:

        raise ValueError(
            f"No suitable satellite image "
            f"found for {year}."
        )

    print(
        f"Candidate scenes found: "
        f"{len(items)}"
    )

    # -------------------------------------------------------------
    # Footprint filtering
    # -------------------------------------------------------------
    #
    # Remove scenes whose footprint does not intersect
    # the AOI at all.
    #
    # This does NOT perform any raster processing.
    # -------------------------------------------------------------

    intersecting_items = []

    for image in items:

        if _scene_intersects_aoi(
            image,
            geometry
        ):

            intersecting_items.append(
                image
            )

    print(
        f"Scenes intersecting AOI: "
        f"{len(intersecting_items)}"
    )

    # If the footprint check somehow returns nothing,
    # fall back to the original candidate list.
    if not intersecting_items:

        print(
            "Warning: no footprint intersection "
            "was detected."
        )

        print(
            "Falling back to all candidate scenes."
        )

        intersecting_items = items

    # -------------------------------------------------------------
    # Calculate approximate AOI overlap
    # -------------------------------------------------------------

    ranked_items = []

    for image in intersecting_items:

        overlap_ratio = (
            _scene_overlap_ratio(
                image,
                geometry
            )
        )

        cloud_cover = image.properties.get(
            "eo:cloud_cover",
            100
        )

        ranked_items.append(
            (
                image,
                overlap_ratio,
                cloud_cover
            )
        )

    # -------------------------------------------------------------
    # Sort candidates
    #
    # PRIMARY:
    #     AOI coverage
    #
    # SECONDARY:
    #     cloud cover
    #
    # This means a scene that actually covers the AOI
    # is preferred over a very cloudy-free scene that
    # only covers a small part of the AOI.
    # -------------------------------------------------------------

    ranked_items.sort(
        key=lambda item: (
            -item[1],
            item[2]
        )
    )

    items = [
        item[0]
        for item in ranked_items
    ]

    # -------------------------------------------------------------
    # Display ranking
    # -------------------------------------------------------------

    print(
        "\nTop candidate scenes:"
    )

    for index, (
        image,
        overlap_ratio,
        cloud_cover
    ) in enumerate(
        ranked_items[:10],
        start=1
    ):

        print(
            f"{index}. "
            f"{image.id} | "
            f"AOI overlap: "
            f"{overlap_ratio:.1%} | "
            f"Cloud: "
            f"{cloud_cover}"
        )

    print(
        "\nSelected first candidate:"
    )

    print(
        items[0].id
    )

    print(
        "Cloud cover:",
        items[0].properties.get(
            "eo:cloud_cover"
        )
    )

    return items


# ---------------------------------------------------------------------
# Raster window reader
# ---------------------------------------------------------------------

def _read_window(
    href,
    left,
    bottom,
    right,
    top,
    target_shape=None,
    resampling=Resampling.nearest
):

    start_time = time.perf_counter()

    with rasterio.open(
        href
    ) as src:

        bounds_in_crs = transform_bounds(
            "EPSG:4326",
            src.crs,
            left,
            bottom,
            right,
            top
        )

        window = from_bounds(
            *bounds_in_crs,
            transform=src.transform
        )

        if target_shape is None:

            out_shape = (
                max(
                    1,
                    int(
                        round(
                            window.height
                        )
                    )
                ),
                max(
                    1,
                    int(
                        round(
                            window.width
                        )
                    )
                )
            )

        else:

            out_shape = target_shape

        data = src.read(
            1,
            window=window,
            boundless=True,
            fill_value=0,
            out_shape=out_shape,
            resampling=resampling
        ).astype(float)

        nodata = (
            src.nodata
            if src.nodata is not None
            else 0
        )

        transform = src.window_transform(
            window
        )

        crs = src.crs

    elapsed = (
        time.perf_counter()
        - start_time
    )

    print(
        f"Raster read completed in "
        f"{elapsed:.2f}s"
    )

    return (
        data,
        nodata,
        transform,
        crs
    )


# ---------------------------------------------------------------------
# Read exact polygon AOI
# ---------------------------------------------------------------------

def _read_aoi_data(
    image,
    geometry
):

    print(
        f"\nReading satellite data for scene: "
        f"{image.id}"
    )

    # ---------------------------------------------------------------
    # Polygon bounding box
    # ---------------------------------------------------------------

    left, bottom, right, top = bounds(
        geometry
    )

    print(
        "AOI bounds:",
        f"{left:.5f}, {bottom:.5f}, "
        f"{right:.5f}, {top:.5f}"
    )

    # ---------------------------------------------------------------
    # B03 = Green, 10 m
    # ---------------------------------------------------------------

    print(
        "Reading B03 (Green, 10 m)..."
    )

    green, green_nodata, green_transform, green_crs = (
        _read_window(
            image.assets["B03"].href,
            left,
            bottom,
            right,
            top
        )
    )

    print(
        f"B03 loaded: "
        f"{green.shape[0]} x "
        f"{green.shape[1]}"
    )

    # ---------------------------------------------------------------
    # B11 = SWIR, 20 m
    #
    # Resample to B03 10 m grid.
    # ---------------------------------------------------------------

    print(
        "Reading B11 (SWIR, 20 m) "
        "and resampling to B03 grid..."
    )

    swir, swir_nodata, swir_transform, swir_crs = (
        _read_window(
            image.assets["B11"].href,
            left,
            bottom,
            right,
            top,
            target_shape=green.shape,
            resampling=Resampling.bilinear
        )
    )

    print(
        f"B11 loaded/resampled: "
        f"{swir.shape[0]} x "
        f"{swir.shape[1]}"
    )

    # ---------------------------------------------------------------
    # Shape check
    # ---------------------------------------------------------------

    if swir.shape != green.shape:

        raise ValueError(
            f"B03/B11 shape mismatch for "
            f"{image.id}: "
            f"{green.shape} vs "
            f"{swir.shape}"
        )

    # ---------------------------------------------------------------
    # Polygon transformation
    # ---------------------------------------------------------------

    print(
        "Creating exact polygon mask..."
    )

    polygon_raster = transform_geom(
        "EPSG:4326",
        green_crs,
        geometry
    )

    inside_polygon = geometry_mask(
        [polygon_raster],
        out_shape=green.shape,
        transform=green_transform,
        invert=True
    )

    # ---------------------------------------------------------------
    # Basic valid pixels
    # ---------------------------------------------------------------

    valid = (
        (green != green_nodata)
        &
        (swir != swir_nodata)
    )

    valid &= inside_polygon

    # ---------------------------------------------------------------
    # SCL masking
    # ---------------------------------------------------------------

    if "SCL" in image.assets:

        print(
            "Reading SCL and applying "
            "cloud/invalid-pixel mask..."
        )

        scl, _, _, _ = _read_window(
            image.assets["SCL"].href,
            left,
            bottom,
            right,
            top,
            target_shape=green.shape,
            resampling=Resampling.nearest
        )

        for code in SCL_EXCLUDE_VALUES:

            valid &= scl != code

        print(
            "SCL masking complete."
        )

    print(
        "Satellite data processing complete."
    )

    return (
        green,
        swir,
        valid,
        inside_polygon
    )


# ---------------------------------------------------------------------
# Yearly water analysis
# ---------------------------------------------------------------------

def calculate_yearly_water(
    latitude,
    longitude,
    geometry,
    year
):

    year_start_time = time.perf_counter()

    print(
        "\n========================================"
    )

    print(
        f"STARTING WATER ANALYSIS: {year}"
    )

    print(
        "========================================"
    )

    # ---------------------------------------------------------------
    # Candidate scenes
    # ---------------------------------------------------------------

    candidates = get_candidate_sentinel_images(
        geometry,
        year
    )

    last_error = None

    # ---------------------------------------------------------------
    # Try candidates
    # ---------------------------------------------------------------

    for scene_number, image in enumerate(
        candidates,
        start=1
    ):

        print(
            f"\nTrying scene "
            f"{scene_number}/"
            f"{len(candidates)}:"
        )

        print(
            image.id
        )

        try:

            (
                green,
                swir,
                valid,
                inside_polygon
            ) = _read_aoi_data(
                image,
                geometry
            )

        except Exception as error:

            last_error = error

            print(
                f"Scene failed: {error}"
            )

            continue

        # -----------------------------------------------------------
        # Polygon pixels
        # -----------------------------------------------------------

        polygon_pixels = int(
            inside_polygon.sum()
        )

        if polygon_pixels == 0:

            last_error = ValueError(
                "Polygon does not overlap "
                "the satellite image."
            )

            print(
                "Scene rejected: polygon "
                "does not overlap image."
            )

            continue

        # -----------------------------------------------------------
        # Valid pixel fraction
        # -----------------------------------------------------------

        valid_fraction = (
            valid.sum()
            /
            polygon_pixels
        )

        print(
            f"Valid pixel fraction: "
            f"{valid_fraction:.2%}"
        )

        # -----------------------------------------------------------
        # IMPORTANT:
        # Keep the original 50% validation.
        # -----------------------------------------------------------

        if valid_fraction < MIN_VALID_PIXEL_FRACTION:

            last_error = ValueError(
                f"Only {valid_fraction:.0%} "
                f"valid pixels inside "
                f"polygon for {image.id}."
            )

            print(
                "Scene rejected: valid coverage "
                f"is below "
                f"{MIN_VALID_PIXEL_FRACTION:.0%}."
            )

            continue

        # -----------------------------------------------------------
        # Scale Sentinel-2 reflectance
        # -----------------------------------------------------------

        green_scaled = (
            green / SENTINEL2_SCALE
        )

        swir_scaled = (
            swir / SENTINEL2_SCALE
        )

        # -----------------------------------------------------------
        # MNDWI
        # -----------------------------------------------------------

        print(
            "Calculating MNDWI..."
        )

        mndwi = calculate_mndwi(
            green_scaled,
            swir_scaled
        )

        mndwi_valid = np.where(
            valid,
            mndwi,
            np.nan
        )

        # -----------------------------------------------------------
        # Water classification
        #
        # MNDWI > 0
        # -----------------------------------------------------------

        print(
            "Classifying water pixels..."
        )

        water_pixels = (
            mndwi_valid
            >
            WATER_MNDWI_THRESHOLD
        )

        # -----------------------------------------------------------
        # Water percentage
        # -----------------------------------------------------------

        water_percentage = (
            np.nansum(
                water_pixels
            )
            /
            valid.sum()
        ) * 100

        # -----------------------------------------------------------
        # Average MNDWI
        # -----------------------------------------------------------

        average_mndwi = float(
            np.nanmean(
                mndwi_valid
            )
        )

        # -----------------------------------------------------------
        # Timing
        # -----------------------------------------------------------

        year_elapsed = (
            time.perf_counter()
            -
            year_start_time
        )

        # -----------------------------------------------------------
        # Output
        # -----------------------------------------------------------

        print(
            f"\n========== {year} =========="
        )

        print(
            "Satellite image:",
            image.id
        )

        print(
            "Date:",
            image.datetime
        )

        print(
            "Scene cloud cover:",
            image.properties.get(
                "eo:cloud_cover"
            )
        )

        print(
            "Exact polygon pixels:",
            polygon_pixels
        )

        print(
            "Valid polygon pixels:",
            int(valid.sum())
        )

        print(
            f"Valid polygon coverage: "
            f"{valid_fraction:.0%}"
        )

        print(
            f"Water coverage: "
            f"{water_percentage:.2f}%"
        )

        print(
            f"Average MNDWI: "
            f"{average_mndwi:.3f}"
        )

        print(
            f"Total processing time "
            f"for {year}: "
            f"{year_elapsed:.2f}s"
        )

        print(
            "=============================="
        )

        return {
            "year": year,
            "water_percentage": water_percentage,
            "average_mndwi": average_mndwi,
            "image_id": image.id,
            "image_date": str(
                image.datetime
            ),
            "cloud_cover": image.properties.get(
                "eo:cloud_cover"
            ),
            "valid_pixel_fraction": valid_fraction
        }

    # ---------------------------------------------------------------
    # No suitable scene
    # ---------------------------------------------------------------

    raise ValueError(
        f"No scene for {year} had enough "
        f"valid coverage inside the exact "
        f"polygon "
        f"(last error: {last_error})"
    )


# ---------------------------------------------------------------------
# Standalone testing
# ---------------------------------------------------------------------

def main():

    from location import get_coordinates

    location_name = input(
        "Enter location: "
    )

    start_year = int(
        input(
            "Enter start year: "
        )
    )

    end_year = int(
        input(
            "Enter end year: "
        )
    )

    location = get_coordinates(
        location_name
    )

    latitude = location[
        "latitude"
    ]

    longitude = location[
        "longitude"
    ]

    geometry = location[
        "geometry"
    ]

    print(
        "\nLocation found:"
    )

    print(
        location["name"]
    )

    print(
        "Latitude:",
        latitude
    )

    print(
        "Longitude:",
        longitude
    )

    print(
        "Boundary type:",
        geometry["type"]
    )

    results = []

    # ---------------------------------------------------------------
    # Year-by-year analysis
    # ---------------------------------------------------------------

    for year in range(
        start_year,
        end_year + 1
    ):

        try:

            result = calculate_yearly_water(
                latitude=latitude,
                longitude=longitude,
                geometry=geometry,
                year=year
            )

            results.append(
                result
            )

        except Exception as error:

            print(
                f"Could not analyze "
                f"{year}: {error}"
            )

    # ---------------------------------------------------------------
    # Water trend
    # ---------------------------------------------------------------

    print(
        "\n\n=============================="
    )

    print(
        f"WATER TREND "
        f"{start_year}-{end_year}"
    )

    print(
        "=============================="
    )

    for result in results:

        print(
            f"{result['year']} : "
            f"{result['water_percentage']:.2f}%"
        )

    # ---------------------------------------------------------------
    # Overall change
    # ---------------------------------------------------------------

    if len(results) >= 2:

        first = results[0][
            "water_percentage"
        ]

        last = results[-1][
            "water_percentage"
        ]

        change = last - first

        print(
            "\nOverall change:"
        )

        print(
            f"{change:+.2f} "
            f"percentage points"
        )

        if first != 0:

            print(
                f"{(change / first) * 100:+.2f}%"
            )

        else:

            print(
                "Percentage change undefined "
                "(starting value was 0%)."
            )


# ---------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------

if __name__ == "__main__":
    main()