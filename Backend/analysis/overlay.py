"""
Render a colored index raster (NDVI / MNDWI / NDBI) as a PNG
for the frontend map overlay.

This does not change index values. It only visualizes arrays
already computed by the analysis modules.
"""

import re
import struct
import zlib
from pathlib import Path

import numpy as np
from rasterio.features import bounds as geom_bounds


OVERLAY_DIR = (
    Path(__file__).resolve().parent.parent
    / "static"
    / "overlays"
)

MAX_OVERLAY_DIM = 512


# Colormap stops: (normalized 0–1, RGB)
COLORMAPS = {
    "ndvi": [
        (0.0, (165, 0, 38)),
        (0.25, (215, 48, 39)),
        (0.5, (254, 224, 139)),
        (0.75, (145, 207, 96)),
        (1.0, (0, 104, 55)),
    ],
    "mndwi": [
        (0.0, (247, 251, 255)),
        (0.35, (158, 202, 225)),
        (0.7, (49, 130, 189)),
        (1.0, (8, 48, 107)),
    ],
    "ndbi": [
        (0.0, (255, 255, 204)),
        (0.4, (254, 217, 118)),
        (0.7, (253, 141, 60)),
        (1.0, (153, 52, 4)),
    ],
}

INDEX_RANGES = {
    "ndvi": (-0.2, 0.8),
    "mndwi": (-0.5, 0.5),
    "ndbi": (-0.5, 0.5),
}


def _downsample(array, max_dim=MAX_OVERLAY_DIM):

    height, width = array.shape

    longest = max(height, width)

    if longest <= max_dim:
        return array

    step = int(np.ceil(longest / max_dim))

    return array[::step, ::step]


def _interpolate_colormap(normalized, stops):

    normalized = np.clip(normalized, 0.0, 1.0)

    red = np.zeros_like(normalized)
    green = np.zeros_like(normalized)
    blue = np.zeros_like(normalized)

    for index in range(len(stops) - 1):

        t0, c0 = stops[index]
        t1, c1 = stops[index + 1]

        mask = (normalized >= t0) & (normalized <= t1)

        if not np.any(mask):
            continue

        span = t1 - t0

        if span == 0:
            fraction = 0.0
        else:
            fraction = (normalized[mask] - t0) / span

        red[mask] = c0[0] + fraction * (c1[0] - c0[0])
        green[mask] = c0[1] + fraction * (c1[1] - c0[1])
        blue[mask] = c0[2] + fraction * (c1[2] - c0[2])

    return red, green, blue


def colorize_index(index_array, colormap="ndvi"):

    vmin, vmax = INDEX_RANGES.get(
        colormap,
        (-1.0, 1.0)
    )

    stops = COLORMAPS.get(
        colormap,
        COLORMAPS["ndvi"]
    )

    sampled = _downsample(
        np.asarray(index_array, dtype=float)
    )

    finite = np.isfinite(sampled)

    normalized = np.zeros_like(sampled, dtype=float)

    span = vmax - vmin

    if span != 0:
        normalized[finite] = (
            (sampled[finite] - vmin) / span
        )

    red, green, blue = _interpolate_colormap(
        normalized,
        stops
    )

    height, width = sampled.shape

    rgba = np.zeros(
        (height, width, 4),
        dtype=np.uint8
    )

    rgba[..., 0] = np.clip(red, 0, 255).astype(np.uint8)
    rgba[..., 1] = np.clip(green, 0, 255).astype(np.uint8)
    rgba[..., 2] = np.clip(blue, 0, 255).astype(np.uint8)
    rgba[..., 3] = np.where(finite, 200, 0).astype(np.uint8)

    return rgba


def _png_chunk(tag, data):

    crc = zlib.crc32(tag + data) & 0xFFFFFFFF

    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", crc)
    )


def write_png(path, rgba):

    height, width, channels = rgba.shape

    color_type = 6 if channels == 4 else 2

    raw = b"".join(
        b"\x00" + rgba[row].tobytes()
        for row in range(height)
    )

    ihdr = struct.pack(
        ">IIBBBBB",
        width,
        height,
        8,
        color_type,
        0,
        0,
        0
    )

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )

    Path(path).write_bytes(png_bytes)


def _safe_name(name):

    cleaned = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        str(name)
    )

    return cleaned[:80] or "overlay"


def save_index_overlay(
    index_array,
    geometry,
    name,
    colormap="ndvi"
):
    """
    Write a PNG overlay and return URL + Leaflet bounds.

    On failure, return an empty dict so analysis still succeeds.
    """

    try:

        OVERLAY_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        rgba = colorize_index(
            index_array,
            colormap=colormap
        )

        filename = f"{_safe_name(name)}.png"
        path = OVERLAY_DIR / filename

        write_png(path, rgba)

        left, bottom, right, top = geom_bounds(
            geometry
        )

        return {
            "overlay_url": f"/static/overlays/{filename}",
            "overlay_bounds": [
                [float(bottom), float(left)],
                [float(top), float(right)]
            ]
        }

    except Exception as error:

        print(
            f"Overlay render skipped: {error}"
        )

        return {}
