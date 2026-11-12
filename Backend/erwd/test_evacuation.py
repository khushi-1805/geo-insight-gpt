
import unittest

import numpy as np
from affine import Affine
from rasterio.crs import CRS

from evacuation.dry_area_detector import detect_large_dry_areas


class TestDryAreaDetector(unittest.TestCase):

    def setUp(self):
        # 100 x 100 raster with 10 m x 10 m pixels.
        self.transform = Affine(
            10, 0, 500000,
            0, -10, 1400000,
        )
        self.crs = CRS.from_epsg(32643)  # Projected CRS in metres.

    def test_large_area_is_detected(self):
        # True = flooded, False = dry.
        flood_mask = np.ones((100, 100), dtype=bool)

        # 40 x 40 pixels = 160,000 m².
        flood_mask[10:50, 10:50] = False

        areas = detect_large_dry_areas(
            flood_mask,
            self.transform,
            self.crs,
            min_area_m2=10_000,
        )

        self.assertEqual(len(areas), 1)
        self.assertAlmostEqual(areas[0].area_m2, 160_000)
        self.assertEqual(areas[0].pixel_count, 1600)

    def test_small_patch_is_excluded(self):
        flood_mask = np.ones((100, 100), dtype=bool)

        # 10 x 10 pixels = 10,000 m².
        flood_mask[10:20, 10:20] = False

        areas = detect_large_dry_areas(
            flood_mask,
            self.transform,
            self.crs,
            min_area_m2=15_000,
        )

        self.assertEqual(areas, [])

    def test_separate_areas_are_not_merged(self):
        flood_mask = np.ones((100, 100), dtype=bool)

        flood_mask[5:25, 5:25] = False
        flood_mask[60:85, 60:85] = False

        areas = detect_large_dry_areas(
            flood_mask,
            self.transform,
            self.crs,
            min_area_m2=10_000,
        )

        self.assertEqual(len(areas), 2)
        self.assertGreater(
            areas[0].area_m2,
            areas[1].area_m2,
        )

    def test_boundary_touching_area_is_detected(self):
        flood_mask = np.ones((100, 100), dtype=bool)

        # A large dry region touches the raster's upper-left boundary.
        flood_mask[0:40, 0:40] = False

        areas = detect_large_dry_areas(
            flood_mask,
            self.transform,
            self.crs,
            min_area_m2=10_000,
        )

        self.assertEqual(len(areas), 1)
        self.assertAlmostEqual(areas[0].area_m2, 160_000)

    
    def test_unknown_pixels_are_excluded(self):
        flood_mask = np.ones((100, 100), dtype=bool)
        valid_mask = np.ones((100, 100), dtype=bool)

        # A 40 x 40 region appears dry.
        flood_mask[10:50, 10:50] = False

        # But a strip of that region has unknown data.
        valid_mask[10:50, 10:15] = False

        areas = detect_large_dry_areas(
            flood_mask,
            self.transform,
            self.crs,
            min_area_m2=10_000,
            valid_mask=valid_mask,
        )

        # The unknown strip must not be counted as dry.
        self.assertEqual(len(areas), 1)
        self.assertAlmostEqual(areas[0].area_m2, 140_000)
        self.assertEqual(areas[0].pixel_count, 1400)

if __name__ == "__main__":
    unittest.main(verbosity=2)
