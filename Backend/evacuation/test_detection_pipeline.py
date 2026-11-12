
import unittest
from unittest.mock import patch

import numpy as np
from rasterio.transform import from_origin
from rasterio.crs import CRS

from evacuation.pipeline import detect_evacuation_dry_areas
from evacuation.dry_area_detector import DryArea


class TestDetectionPipeline(unittest.TestCase):

    @patch("evacuation.pipeline.detect_large_dry_areas")
    @patch("evacuation.pipeline.get_flood_raster_metadata")
    @patch("evacuation.pipeline.detect_flood")
    @patch("evacuation.pipeline.load_flood_bands")
    @patch("evacuation.pipeline.build_valid_pixel_mask")
    @patch("evacuation.pipeline.download_and_clip_bands")
    @patch("evacuation.pipeline.find_evacuation_satellite_scene")
    def test_pipeline_passes_valid_mask_to_detector(
        self,
        mock_find_scene,
        mock_download,
        mock_validity,
        mock_load,
        mock_detect_flood,
        mock_metadata,
        mock_detect_areas,
    ):
        mock_find_scene.return_value = {
            "search_area": {"type": "Polygon", "coordinates": []},
            "scene": {
                "id": "synthetic-scene",
                "date": "2026-10-20T00:00:00Z",
                "cloud_cover": 5,
                "assets": {},
            },
        }

        mock_validity.return_value = np.ones((10, 10), dtype=bool)
        mock_load.return_value = np.zeros((6, 10, 10), dtype=np.float32)
        mock_detect_flood.return_value = (
            np.zeros((10, 10), dtype=np.uint8),
            np.zeros((10, 10), dtype=np.float32),
        )
        mock_metadata.return_value = {
            "transform": from_origin(500000, 1430000, 10, 10),
            "crs": CRS.from_epsg(32643),
            "width": 10,
            "height": 10,
        }

        mock_detect_areas.return_value = [
            DryArea(
                area_m2=10000,
                center_lat=12.97,
                center_lon=77.59,
                pixel_count=100,
            )
        ]

        result = detect_evacuation_dry_areas(
            latitude=12.9716,
            longitude=77.5946,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(
            result["verification_status"],
            "unverified",
        )

        mock_detect_areas.assert_called_once()
        kwargs = mock_detect_areas.call_args.kwargs
        np.testing.assert_array_equal(
            kwargs["valid_mask"],
            mock_validity.return_value,
        )


if __name__ == "__main__":
    unittest.main()
