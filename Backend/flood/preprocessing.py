import os
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject


FLOOD_BANDS = [
    "B02",
    "B03",
    "B04",
    "B8A",
    "B11",
    "B12",
]

SENTINEL_SCALE = 0.0001

PRITHVI_MEANS = np.array([
    0.14245495,
    0.13921481,
    0.12434631,
    0.31420089,
    0.20743526,
    0.12046503,
], dtype=np.float32)

PRITHVI_STDS = np.array([
    0.04036231,
    0.04186983,
    0.05267646,
    0.08222210,
    0.06834774,
    0.05294205,
], dtype=np.float32)

def load_flood_bands(data_dir="flood_data", normalize=True):
    # B02 is our reference 10 m grid
    reference_path = os.path.join(data_dir, "B02.tif")

    with rasterio.open(reference_path) as reference:
        reference_array = reference.read(1)
        reference_transform = reference.transform
        reference_crs = reference.crs
        reference_shape = reference_array.shape

    band_arrays = []

    for band in FLOOD_BANDS:
        path = os.path.join(data_dir, f"{band}.tif")

        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Band file not found: {path}"
            )

        with rasterio.open(path) as src:

            if band == "B02":
                array = src.read(1).astype(np.float32)

            else:
                array = np.empty(
                    reference_shape,
                    dtype=np.float32
                )

                reproject(
                    source=rasterio.band(src, 1),
                    destination=array,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=reference_transform,
                    dst_crs=reference_crs,
                    resampling=Resampling.bilinear,
                )

            band_arrays.append(array)

    stacked = np.stack(
        band_arrays,
        axis=0
    )

    # Sentinel-2 digital values → reflectance
    stacked = stacked * SENTINEL_SCALE

    # Only normalize when preparing data for Prithvi
    if normalize:
        stacked = (
            stacked
            - PRITHVI_MEANS[:, None, None]
        ) / PRITHVI_STDS[:, None, None]

    return stacked

def create_prithvi_patch(image, patch_size=224):
    """
    Create a square patch for Prithvi while preserving
    the original pixel values and spatial proportions.
    """

    bands, height, width = image.shape

    if bands != 6:
        raise ValueError(
            f"Expected 6 bands, got {bands}"
        )

    if height < patch_size or width < patch_size:
        raise ValueError(
            f"Image is too small for a {patch_size}x{patch_size} patch. "
            f"Current size: {height}x{width}"
        )

    # Center crop
    start_y = (height - patch_size) // 2
    start_x = (width - patch_size) // 2

    patch = image[
        :,
        start_y:start_y + patch_size,
        start_x:start_x + patch_size,
    ]

    return patch

def inspect_prithvi_patch(patch):
    if patch.shape != (6, 224, 224):
        raise ValueError(
            f"Expected (6, 224, 224), got {patch.shape}"
        )

    if not np.isfinite(patch).all():
        raise ValueError("Patch contains NaN or infinite values.")

    print("\n===== PRITHVI PATCH CHECK =====")

    for index, band in enumerate(FLOOD_BANDS):
        band_data = patch[index]

        print(
            f"{band}: "
            f"min={band_data.min():.4f}, "
            f"max={band_data.max():.4f}, "
            f"mean={band_data.mean():.4f}, "
            f"std={band_data.std():.4f}"
        )

    print("Shape:", patch.shape)
    print("Finite:", np.isfinite(patch).all())
    print("===============================\n")

def get_flood_raster_metadata(data_dir="flood_data"):
    """
    Get the spatial metadata needed to map
    TomTom route coordinates onto the satellite raster.
    """

    reference_path = os.path.join(
        data_dir,
        "B02.tif"
    )

    with rasterio.open(reference_path) as src:
        return {
            "transform": src.transform,
            "crs": src.crs,
            "width": src.width,
            "height": src.height,
        }