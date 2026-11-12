
import unittest

from shapely.geometry import shape, Point

from evacuation.pipeline import create_evacuation_search_area


class TestEvacuationPipeline(unittest.TestCase):

    def test_search_area_is_valid(self):
        area = create_evacuation_search_area(
            latitude=12.9716,
            longitude=77.5946,
            radius_m=3000,
        )

        geometry = shape(area)

        self.assertTrue(geometry.is_valid)
        self.assertEqual(geometry.geom_type, "Polygon")

    def test_search_area_contains_user_location(self):
        latitude = 12.9716
        longitude = 77.5946

        area = create_evacuation_search_area(
            latitude=latitude,
            longitude=longitude,
            radius_m=3000,
        )

        geometry = shape(area)

        self.assertTrue(
            geometry.contains(Point(longitude, latitude))
        )

    def test_invalid_coordinates_are_rejected(self):
        with self.assertRaises(ValueError):
            create_evacuation_search_area(
                latitude=100,
                longitude=77.5946,
            )

    def test_non_positive_radius_is_rejected(self):
        with self.assertRaises(ValueError):
            create_evacuation_search_area(
                latitude=12.9716,
                longitude=77.5946,
                radius_m=0,
            )


if __name__ == "__main__":
    unittest.main()
