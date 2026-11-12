
import unittest

from evacuation.dry_area_detector import DryArea
from evacuation.area_filter import (
    AreaMeasurements,
    filter_area_candidates,
)


class TestAreaFilter(unittest.TestCase):

    def setUp(self):
        self.area = DryArea(
            area_m2=20000,
            center_lat=12.9716,
            center_lon=77.5946,
            pixel_count=200,
        )

    def test_valid_area_is_eligible(self):
        measurements = [
            AreaMeasurements(
                flood_fraction=0.0,
                building_fraction=0.05,
                measurements_valid=True,
                warnings=[],
            )
        ]

        results = filter_area_candidates(
            [self.area], measurements
        )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].eligible)

    def test_flooded_area_is_rejected(self):
        measurements = [
            AreaMeasurements(
                flood_fraction=0.20,
                building_fraction=0.05,
                measurements_valid=True,
                warnings=[],
            )
        ]

        results = filter_area_candidates(
            [self.area], measurements
        )

        self.assertFalse(results[0].eligible)

    def test_building_heavy_area_is_rejected(self):
        measurements = [
            AreaMeasurements(
                flood_fraction=0.0,
                building_fraction=0.30,
                measurements_valid=True,
                warnings=[],
            )
        ]

        results = filter_area_candidates(
            [self.area], measurements
        )

        self.assertFalse(results[0].eligible)

    def test_missing_flood_measurement_is_rejected(self):
        measurements = [
            AreaMeasurements(
                flood_fraction=None,
                building_fraction=0.05,
                measurements_valid=True,
                warnings=[],
            )
        ]

        results = filter_area_candidates(
            [self.area], measurements
        )

        self.assertFalse(results[0].eligible)

    def test_invalid_measurements_are_rejected(self):
        measurements = [
            AreaMeasurements(
                flood_fraction=0.0,
                building_fraction=0.05,
                measurements_valid=False,
                warnings=["Measurement data is invalid"],
            )
        ]

        results = filter_area_candidates(
            [self.area], measurements
        )

        self.assertFalse(results[0].eligible)


if __name__ == "__main__":
    unittest.main()
