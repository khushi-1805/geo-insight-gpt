import numpy as np

from flood.preprocessing import load_flood_bands
from flood.flood_detection import (
    detect_flood,
    flood_statistics,
)


IMAGE_DIR = "flood_data"


print("Loading Sentinel-2 data...")

image = load_flood_bands(
    IMAGE_DIR,
    normalize=False
)

print("Image shape:", image.shape)


print("Detecting water/flood areas...")

mask, mndwi = detect_flood(
    image,
    threshold=0.0,
)


stats = flood_statistics(mask)


print()
print("========== FLOOD DETECTION ==========")
print(
    "Flood pixels:",
    stats["flood_pixels"]
)
print(
    "Total pixels:",
    stats["total_pixels"]
)
print(
    f"Detected water/flood area: "
    f"{stats['flood_percentage']:.2f}%"
)
print(
    "MNDWI min:",
    float(np.min(mndwi))
)
print(
    "MNDWI max:",
    float(np.max(mndwi))
)
print(
    "MNDWI mean:",
    float(np.mean(mndwi))
)
print("====================================")