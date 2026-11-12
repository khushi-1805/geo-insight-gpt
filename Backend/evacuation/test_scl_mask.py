import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from shapely.geometry import box, mapping

from evacuation.pipeline import build_valid_pixel_mask


class TestSCLCloudMask(unittest.TestCase):
    def test_cloud_shadow_and_cloud_classes_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # Synthetic UTM zone 43N raster near Bengaluru.
            transform = from_origin(500000, 1430000, 10, 10)
            profile = {
                "driver": "GTiff",
                "height": 4,
                "width": 4,
                "count": 1,
                "dtype": "uint16",
                "crs": "EPSG:32643",
                "transform": transform,
                "nodata": 0,
            }

            reflectance = np.full((4, 4), 1000, dtype=np.uint16)
            for band in ("B02", "B03", "B04", "B8A", "B11", "B12"):
                with rasterio.open(root / f"{band}.tif", "w", **profile) as dst:
                    dst.write(reflectance, 1)

            # Search geometry must be WGS84 because build_valid_pixel_mask
            # explicitly transforms EPSG:4326 into the raster CRS.
            left, bottom, right, top = transform_bounds(
                "EPSG:32643", "EPSG:4326",
                500000, 1429960, 500040, 1430000,
            )
            search = mapping(box(left, bottom, right, top))

            # SCL is 20 m, so each class maps to a 2x2 block on the 10 m grid.
            scl_profile = dict(profile)
            scl_profile.update(
                height=2,
                width=2,
                dtype="uint8",
                transform=from_origin(500000, 1430000, 20, 20),
                nodata=0,
            )
            scl = np.array([[4, 8], [3, 9]], dtype=np.uint8)
            with rasterio.open(root / "SCL.tif", "w", **scl_profile) as dst:
                dst.write(scl, 1)

            valid = build_valid_pixel_mask(str(root), search)

            self.assertTrue(valid[0, 0])    # vegetation class 4
            self.assertFalse(valid[0, 2])   # medium-probability cloud 8
            self.assertFalse(valid[2, 0])   # cloud shadow 3
            self.assertFalse(valid[2, 2])   # high-probability cloud 9


if __name__ == "__main__":
    unittest.main()
