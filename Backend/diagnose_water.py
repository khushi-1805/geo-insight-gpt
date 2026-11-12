import os
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling

from flood.preprocessing import load_flood_bands
from flood.flood_detection import calculate_mndwi_from_reflectance
from evacuation.pipeline import (
    build_valid_pixel_mask,
    create_evacuation_search_area,
)

folder = r"evacuation_data\run_d873e9290505"

# 1. Recreate the same search area used by the API
search_area = create_evacuation_search_area(
    latitude=12.9716,
    longitude=77.5946,
    radius_m=3000,
)

# 2. Load reflectance bands
image = load_flood_bands(folder, normalize=False)

# 3. Calculate MNDWI
mndwi = calculate_mndwi_from_reflectance(image)

# 4. Build the actual validity mask
valid = build_valid_pixel_mask(folder, search_area)

print("\n--- MNDWI STATISTICS ---")

values = mndwi[valid]

print("Valid pixels:", len(values))
print("Min:", values.min())
print("Max:", values.max())
print("Mean:", values.mean())
print("Percentiles:", np.percentile(values, [5, 25, 50, 75, 90, 95, 99]))

# 5. Compare different MNDWI thresholds
print("\n--- MNDWI THRESHOLD COMPARISON ---")

for threshold in [-0.2, -0.1, 0.0, 0.1, 0.2, 0.3]:
    water = (mndwi > threshold) & valid
    print(
        f"Threshold {threshold:>5}: "
        f"{water.sum():>8} water pixels "
        f"({water.sum() / valid.sum() * 100:.2f}%)"
    )

# 6. Align SCL to the B02 10 m grid
scl_path = os.path.join(folder, "SCL.tif")
b02_path = os.path.join(folder, "B02.tif")

with rasterio.open(b02_path) as reference:
    profile = reference.profile.copy()
    height = reference.height
    width = reference.width
    transform = reference.transform
    crs = reference.crs

with rasterio.open(scl_path) as src:
    scl_aligned = np.zeros((height, width), dtype=np.uint8)

    reproject(
        source=rasterio.band(src, 1),
        destination=scl_aligned,
        src_transform=src.transform,
        src_crs=src.crs,
        dst_transform=transform,
        dst_crs=crs,
        resampling=Resampling.nearest,
    )

# 7. Compare MNDWI water indicator with SCL water class 6
scl_water = (scl_aligned == 6) & valid
mndwi_water = (mndwi > 0.0) & valid

print("\n--- SCL vs MNDWI ---")
print("SCL water pixels:", scl_water.sum())
print("MNDWI water pixels:", mndwi_water.sum())

print(
    "Agreement:",
    np.mean(scl_water == mndwi_water) * 100,
    "%"
)

print(
    "Both classify water:",
    np.sum(scl_water & mndwi_water)
)

print(
    "SCL water, MNDWI dry:",
    np.sum(scl_water & ~mndwi_water)
)

print(
    "MNDWI water, SCL non-water:",
    np.sum(mndwi_water & ~scl_water)
)

print("\n--- COMPLETE ---")