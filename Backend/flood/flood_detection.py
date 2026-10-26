import numpy as np


def calculate_mndwi_from_reflectance(image):
    """
    Calculate MNDWI from Sentinel-2 reflectance.

    image band order:
    0 = B02
    1 = B03
    2 = B04
    3 = B8A
    4 = B11
    5 = B12
    """

    green = image[1].astype(np.float32)
    swir1 = image[4].astype(np.float32)

    denominator = green + swir1

    mndwi = np.divide(
        green - swir1,
        denominator,
        out=np.zeros_like(green),
        where=np.abs(denominator) > 1e-6,
    )

    # Remove invalid numerical values
    mndwi = np.nan_to_num(
        mndwi,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    return mndwi


def detect_flood(image, threshold=0.0):

    mndwi = calculate_mndwi_from_reflectance(image)

    flood_mask = (
        mndwi > threshold
    ).astype(np.uint8)

    return flood_mask, mndwi


def flood_statistics(flood_mask):

    total_pixels = flood_mask.size
    flood_pixels = int(np.sum(flood_mask == 1))

    percentage = (
        flood_pixels / total_pixels * 100
        if total_pixels > 0
        else 0.0
    )

    return {
        "flood_pixels": flood_pixels,
        "total_pixels": total_pixels,
        "flood_percentage": float(percentage),
    }