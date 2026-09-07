"""
Vegetation trend analysis using Sentinel-2 imagery from Microsoft
Planetary Computer.

The analysis uses the exact Polygon/MultiPolygon returned by the
location resolver instead of a rectangular latitude/longitude AOI.

Processing:
    Location boundary
        ↓
    Bounding box for Sentinel search/read
        ↓
    Exact polygon mask
        ↓
    SCL cloud/shadow/snow masking
        ↓
    NDVI
        ↓
    Vegetation percentage

Performance optimization:
    Candidate Sentinel-2 scenes are checked against the AOI
    footprint before expensive raster reads.

IMPORTANT:
    The vegetation analysis logic itself is unchanged.
"""

import csv
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

from rasterio.features import (
    geometry_mask,
    bounds
)
from rasterio.windows import from_bounds
from rasterio.warp import (
    transform_bounds,
    transform_geom
)
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

# Used ONLY for finding candidate Sentinel-2 scenes.
#
# It is NOT the analysis area.
SEARCH_BUFFER_DEG = 0.1

MAX_SCENE_CLOUD_COVER = 20


# Require at least 50% of the exact polygon
# to contain valid pixels after masking.
MIN_VALID_PIXEL_FRACTION = 0.5


# ---------------------------------------------------------------------
# Vegetation threshold
# ---------------------------------------------------------------------
#
# IMPORTANT:
# Keep this unchanged.
#
# NDVI > 0.3 = vegetation
# ---------------------------------------------------------------------

NDVI_VEGETATION_THRESHOLD = 0.3


# ---------------------------------------------------------------------
# Sentinel-2 Scene Classification Layer values to exclude
# ---------------------------------------------------------------------

SCL_EXCLUDE_VALUES = {
    0,   # no data
    1,   # saturated/defective
    3,   # cloud shadow
    8,   # cloud medium probability
    9,   # cloud high probability
    10,  # thin cirrus
    11   # snow/ice
}


SENTINEL2_SCALE = 10000.0


# ---------------------------------------------------------------------
# NDVI
# ---------------------------------------------------------------------

def calculate_ndvi(
    red,
    nir
):

    denominator = nir + red

    return np.divide(
        nir - red,
        denominator,
        out=np.full_like(
            denominator,
            np.nan,
            dtype=float
        ),
        where=denominator != 0
    )


# ---------------------------------------------------------------------
# Scene footprint / AOI intersection
# ---------------------------------------------------------------------

def _scene_intersects_aoi(
    image,
    geometry
):
    """
    Check whether the Sentinel-2 scene footprint intersects
    the requested AOI.

    This is only a pre-filter.

    The existing 50% valid-pixel check remains the final
    validation after raster data is actually read.
    """

    try:

        from shapely.geometry import shape

        scene_geometry = image.geometry

        if scene_geometry is None:

            return False

        scene_shape = shape(
            scene_geometry
        )

        aoi_shape = shape(
            geometry
        )

        return scene_shape.intersects(
            aoi_shape
        )

    except Exception:

        # If footprint checking fails,
        # do not reject the scene.
        #
        # The existing valid-pixel check
        # will still determine whether the
        # scene is usable.
        return True


# ---------------------------------------------------------------------
# Approximate scene/AOI overlap
# ---------------------------------------------------------------------

def _scene_overlap_ratio(
    image,
    geometry
):
    """
    Estimate the proportion of the AOI covered by
    the Sentinel-2 scene footprint.

    This value is used ONLY to rank candidates.

    It does not replace the existing 50%
    valid-pixel validation.
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
    latitude,
    longitude,
    year,
    geometry=None,
    buffer_deg=SEARCH_BUFFER_DEG
):
    """
    Return Sentinel-2 scenes.

    Original logic preserved:
        - Sentinel-2 L2A
        - full-year search
        - cloud cover < 20%

    Optimization:
        - reuse STAC catalog
        - check scene footprint against AOI
        - prioritize AOI coverage
        - then use cloud cover
    """

    search_start_time = time.perf_counter()

    catalog = get_catalog()

    # -------------------------------------------------------------
    # Bounding box used ONLY for satellite scene search.
    # -------------------------------------------------------------

    bbox = [
        longitude - buffer_deg,
        latitude - buffer_deg,
        longitude + buffer_deg,
        latitude + buffer_deg
    ]

    print(
        f"\nSearching Sentinel-2 scenes for {year}..."
    )

    print(
        f"Search period: "
        f"{year}-01-01 → {year + 1}-01-01"
    )

    print(
        f"Cloud cover limit: "
        f"{MAX_SCENE_CLOUD_COVER}%"
    )

    search = catalog.search(
        collections=[COLLECTION],
        bbox=bbox,
        datetime=(
            f"{year}-01-01/"
            f"{year + 1}-01-01"
        ),
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
    # If exact geometry is available, use scene footprint.
    # -------------------------------------------------------------

    if geometry is not None:

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

        # ---------------------------------------------------------
        # Safety fallback.
        # ---------------------------------------------------------

        if not intersecting_items:

            print(
                "Warning: no footprint intersection "
                "was detected."
            )

            print(
                "Falling back to all candidate scenes."
            )

            intersecting_items = items

        # ---------------------------------------------------------
        # Calculate approximate AOI overlap.
        # ---------------------------------------------------------

        ranked_items = []

        for image in intersecting_items:

            overlap_ratio = (
                _scene_overlap_ratio(
                    image,
                    geometry
                )
            )

            cloud_cover = (
                image.properties.get(
                    "eo:cloud_cover",
                    100
                )
            )

            ranked_items.append(
                (
                    image,
                    overlap_ratio,
                    cloud_cover
                )
            )

        # ---------------------------------------------------------
        # Rank:
        #
        # 1. AOI coverage
        # 2. Cloud cover
        #
        # This is only candidate prioritization.
        # ---------------------------------------------------------

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

    else:

        # ---------------------------------------------------------
        # Fallback to original cloud-cover ordering if geometry
        # isn't supplied.
        # ---------------------------------------------------------

        items.sort(
            key=lambda item:
            item.properties.get(
                "eo:cloud_cover",
                100
            )
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
    top
):
    """
    Read a raster window covering the polygon bounding box.

    The bounding box is only used to efficiently read the
    required raster area.

    Pixels outside the exact polygon are removed later.
    """

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

        data = src.read(
            1,
            window=window,
            boundless=True,
            fill_value=0,
            out_shape=out_shape,
            resampling=Resampling.nearest
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
# Exact polygon AOI processing
# ---------------------------------------------------------------------

def _read_aoi_bands(
    image,
    geometry
):
    """
    Read B04, B08 and SCL for the exact polygon AOI.

    Steps:
        1. Find polygon bounding box.
        2. Read raster data covering the bounding box.
        3. Create an exact polygon mask.
        4. Apply SCL cloud/shadow/snow masking.
        5. Return the combined valid-pixel mask.
    """

    print(
        f"\nReading satellite data for scene: "
        f"{image.id}"
    )

    # ---------------------------------------------------------------
    # Get polygon bounding box
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
    # Read red band
    # ---------------------------------------------------------------

    print(
        "Reading B04 (Red, 10 m)..."
    )

    red, red_nodata, red_transform, red_crs = (
        _read_window(
            image.assets["B04"].href,
            left,
            bottom,
            right,
            top
        )
    )

    print(
        f"B04 loaded: "
        f"{red.shape[0]} x "
        f"{red.shape[1]}"
    )

    # ---------------------------------------------------------------
    # Read NIR band
    # ---------------------------------------------------------------

    print(
        "Reading B08 (NIR, 10 m)..."
    )

    nir, nir_nodata, nir_transform, nir_crs = (
        _read_window(
            image.assets["B08"].href,
            left,
            bottom,
            right,
            top
        )
    )

    print(
        f"B08 loaded: "
        f"{nir.shape[0]} x "
        f"{nir.shape[1]}"
    )

    # ---------------------------------------------------------------
    # Check shape
    # ---------------------------------------------------------------

    if red.shape != nir.shape:

        raise ValueError(
            f"Red/NIR shape mismatch for "
            f"{image.id}: "
            f"{red.shape} vs "
            f"{nir.shape}"
        )

    # ---------------------------------------------------------------
    # Check transform/CRS
    # ---------------------------------------------------------------

    if red_transform != nir_transform:

        raise ValueError(
            f"Red/NIR transform mismatch "
            f"for {image.id}"
        )

    # ---------------------------------------------------------------
    # Transform polygon into raster CRS
    # ---------------------------------------------------------------

    polygon_raster_crs = transform_geom(
        "EPSG:4326",
        red_crs,
        geometry
    )

    # ---------------------------------------------------------------
    # Exact polygon mask
    # ---------------------------------------------------------------

    print(
        "Creating exact polygon mask..."
    )

    inside_polygon = geometry_mask(
        [polygon_raster_crs],
        out_shape=red.shape,
        transform=red_transform,
        invert=True
    )

    # ---------------------------------------------------------------
    # Basic valid-pixel mask
    # ---------------------------------------------------------------

    valid = (
        (red != red_nodata)
        &
        (nir != nir_nodata)
    )

    # IMPORTANT:
    # Only pixels INSIDE the exact polygon are valid.
    valid &= inside_polygon

    # ---------------------------------------------------------------
    # SCL masking
    # ---------------------------------------------------------------

    if "SCL" in image.assets:

        print(
            "Reading SCL and applying "
            "cloud/invalid-pixel mask..."
        )

        with rasterio.open(
            image.assets["SCL"].href
        ) as scl_src:

            # -------------------------------------------------------
            # Transform polygon bounding box into SCL CRS.
            # -------------------------------------------------------

            scl_bounds = transform_bounds(
                "EPSG:4326",
                scl_src.crs,
                left,
                bottom,
                right,
                top
            )

            scl_window = from_bounds(
                *scl_bounds,
                transform=scl_src.transform
            )

            # -------------------------------------------------------
            # Read SCL at the same shape as B04/B08.
            # Nearest-neighbour is retained because SCL
            # contains categorical classes.
            # -------------------------------------------------------

            scl = scl_src.read(
                1,
                window=scl_window,
                boundless=True,
                fill_value=0,
                out_shape=red.shape,
                resampling=Resampling.nearest
            )

        # -----------------------------------------------------------
        # Apply SCL cloud/shadow/snow mask.
        # -----------------------------------------------------------

        for code in SCL_EXCLUDE_VALUES:

            valid &= scl != code

        print(
            "SCL masking complete."
        )

    print(
        "Satellite data processing complete."
    )

    return (
        red,
        nir,
        valid,
        inside_polygon
    )


# ---------------------------------------------------------------------
# Yearly vegetation analysis
# ---------------------------------------------------------------------

def calculate_yearly_vegetation(
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
        f"STARTING VEGETATION ANALYSIS: {year}"
    )

    print(
        "========================================"
    )

    # ---------------------------------------------------------------
    # Candidate scenes
    # ---------------------------------------------------------------

    candidates = get_candidate_sentinel_images(
        latitude=latitude,
        longitude=longitude,
        year=year,
        geometry=geometry
    )

    last_error = None

    # ---------------------------------------------------------------
    # Try scenes.
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
                red,
                nir,
                valid,
                inside_polygon
            ) = _read_aoi_bands(
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
        # Check polygon
        # -----------------------------------------------------------

        polygon_pixels = (
            inside_polygon.sum()
        )

        if polygon_pixels == 0:

            last_error = ValueError(
                "Polygon does not overlap the "
                "satellite image."
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
        # Keep original 50% threshold.
        # -----------------------------------------------------------

        if valid_fraction < MIN_VALID_PIXEL_FRACTION:

            last_error = ValueError(
                f"Only {valid_fraction:.0%} valid pixels "
                f"inside the exact polygon for "
                f"{image.id}."
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

        red_scaled = (
            red / SENTINEL2_SCALE
        )

        nir_scaled = (
            nir / SENTINEL2_SCALE
        )

        # -----------------------------------------------------------
        # NDVI
        # -----------------------------------------------------------

        print(
            "Calculating NDVI..."
        )

        ndvi = calculate_ndvi(
            red_scaled,
            nir_scaled
        )

        # Only exact polygon + valid pixels
        ndvi_valid = np.where(
            valid,
            ndvi,
            np.nan
        )

        # -----------------------------------------------------------
        # Vegetation classification
        #
        # IMPORTANT:
        # Existing threshold remains:
        #
        # NDVI > 0.3
        # -----------------------------------------------------------

        print(
            "Classifying vegetation pixels..."
        )

        vegetation_pixels = (
            ndvi_valid
            >
            NDVI_VEGETATION_THRESHOLD
        )

        # -----------------------------------------------------------
        # Vegetation percentage
        # -----------------------------------------------------------

        vegetation_percentage = (
            np.nansum(
                vegetation_pixels
            )
            /
            valid.sum()
        ) * 100

        # -----------------------------------------------------------
        # Average NDVI
        # -----------------------------------------------------------

        average_ndvi = float(
            np.nanmean(
                ndvi_valid
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
            f"Exact polygon pixels: "
            f"{polygon_pixels}"
        )

        print(
            f"Valid polygon pixels: "
            f"{valid.sum()}"
        )

        print(
            f"Valid polygon coverage: "
            f"{valid_fraction:.0%}"
        )

        print(
            f"Vegetation coverage: "
            f"{vegetation_percentage:.2f}%"
        )

        print(
            f"Average NDVI: "
            f"{average_ndvi:.3f}"
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
            "vegetation_percentage": (
                vegetation_percentage
            ),
            "average_ndvi": average_ndvi,
            "image_id": image.id,
            "image_date": str(
                image.datetime
            ),
            "cloud_cover": image.properties.get(
                "eo:cloud_cover"
            ),
            "valid_pixel_fraction": (
                valid_fraction
            )
        }

    # ---------------------------------------------------------------
    # No suitable scene
    # ---------------------------------------------------------------

    raise ValueError(
        f"No scene for {year} had enough "
        f"cloud-free coverage inside the exact "
        f"polygon "
        f"(last error: {last_error})"
    )


# ---------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------

def save_results_csv(
    results,
    path
):

    if not results:

        return

    fieldnames = list(
        results[0].keys()
    )

    with open(
        path,
        "w",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerows(
            results
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

            results.append(
                calculate_yearly_vegetation(
                    latitude=latitude,
                    longitude=longitude,
                    geometry=geometry,
                    year=year
                )
            )

        except Exception as error:

            print(
                f"Could not analyze "
                f"{year}: {error}"
            )

    # ---------------------------------------------------------------
    # Trend
    # ---------------------------------------------------------------

    print(
        "\n\n=============================="
    )

    print(
        f"VEGETATION TREND "
        f"{start_year}-{end_year}"
    )

    print(
        "=============================="
    )

    for result in results:

        print(
            f"{result['year']} : "
            f"{result['vegetation_percentage']:.2f}%"
        )

    # ---------------------------------------------------------------
    # Overall change
    # ---------------------------------------------------------------

    if len(results) >= 2:

        first = results[0][
            "vegetation_percentage"
        ]

        last = results[-1][
            "vegetation_percentage"
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

        # -----------------------------------------------------------
        # Trend interpretation
        # -----------------------------------------------------------

        if change > 0:

            print(
                "Trend: Vegetation increased."
            )

        elif change < 0:

            print(
                "Trend: Vegetation decreased."
            )

        else:

            print(
                "Trend: Vegetation remained stable."
            )

    # ---------------------------------------------------------------
    # Save CSV
    # ---------------------------------------------------------------

    output_path = Path(
        "vegetation_trend_results.csv"
    )

    save_results_csv(
        results,
        output_path
    )

    print(
        f"\nResults saved to "
        f"{output_path}"
    )

    # ---------------------------------------------------------------
    # Current-year note
    # ---------------------------------------------------------------

    import datetime

    if (
        results
        and
        results[-1]["year"]
        ==
        datetime.date.today().year
    ):

        print(
            f"\nNote: {results[-1]['year']} "
            "only covers through the current "
            "date, so it isn't a like-for-like "
            "comparison with full prior years."
        )


# ---------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------

if __name__ == "__main__":

    main()