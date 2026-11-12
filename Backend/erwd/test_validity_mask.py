
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import mapping, box

from evacuation.pipeline import build_valid_pixel_mask


class TestValidityMask(unittest.TestCase):

    def test_excludes_nodata_and_outside_geometry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)

            transform = from_origin(
                500000, 1000, 10, 10
            )

            # 4x4 raster, with one NoData pixel.
            data = np.ones((4, 4), dtype=np.uint16)
            data[0, 0] = 0

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

            for band in ("B02", "B03", "B04", "B8A", "B11", "B12"):
                with rasterio.open(
                    data_dir / f"{band}.tif",
                    "w",
                    **profile,
                ) as dst:
                    dst.write(data, 1)

            # Geometry covering only the middle portion of the raster.
            search_area = mapping(
                box(
                    500010, 960,
                    500030, 990,
                )
            )

            valid = build_valid_pixel_mask(
                str(data_dir),
                search_area,
            )

            self.assertEqual(valid.shape, (4, 4))
            self.assertFalse(valid[0, 0])
            self.assertFalse(valid[3, 3])
            self.assertTrue(valid[1, 1])

    def test_missing_band_raises_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)

            transform = from_origin(
                500000, 1000, 10, 10
            )

            profile = {
                "driver": "GTiff",
                "height": 2,
                "width": 2,
                "count": 1,
                "dtype": "uint16",
                "crs": "EPSG:32643",
                "transform": transform,
                "nodata": 0,
            }

            with rasterio.open(
                data_dir / "B02.tif",
                "w",
                **profile,
            ) as dst:
                dst.write(
                    np.ones((2, 2), dtype=np.uint16),
                    1,
                )

            with self.assertRaises(FileNotFoundError):
                build_valid_pixel_mask(
                    str(data_dir),
                    mapping(box(500000, 980, 500020, 1000)),
                )


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import mapping, box
from rasterio.warp import transform_bounds

from evacuation.pipeline import build_valid_pixel_mask


class TestValidityMask(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.data_dir = Path(self.temp_dir.name)

        # Small raster located near Bengaluru, in UTM zone 43N.
        self.transform = from_origin(
            500000, 1430000, 10, 10
        )

        self.profile = {
            "driver": "GTiff",
            "height": 4,
            "width": 4,
            "count": 1,
            "dtype": "uint16",
            "crs": "EPSG:32643",
            "transform": self.transform,
            "nodata": 0,
        }

    def create_bands(self, include_all=True):
        bands = ["B02", "B03", "B04", "B8A", "B11", "B12"]

        if not include_all:
            bands = ["B02"]

        data = np.ones((4, 4), dtype=np.uint16)
        data[0, 0] = 0

        for band in bands:
            with rasterio.open(
                self.data_dir / f"{band}.tif",
                "w",
                **self.profile,
            ) as dst:
                dst.write(data, 1)

    def make_search_area(self):
        left, bottom, right, top = transform_bounds(
            "EPSG:32643",
            "EPSG:4326",
            500010, 1429960, 500030, 1429990,
        )

        return mapping(box(left, bottom, right, top))

    def test_excludes_nodata_and_outside_geometry(self):
        self.create_bands()

        valid = build_valid_pixel_mask(
            str(self.data_dir),
            self.make_search_area(),
        )

        self.assertEqual(valid.shape, (4, 4))
        self.assertFalse(valid[0, 0])
        self.assertFalse(valid[3, 3])
        self.assertTrue(valid[1, 1])

    def test_missing_band_raises_error(self):
        self.create_bands(include_all=False)

        with self.assertRaises(FileNotFoundError):
            build_valid_pixel_mask(
                str(self.data_dir),
                self.make_search_area(),
            )


if __name__ == "__main__":
    unittest.main()
