
import unittest

from evacuation.dry_area_detector import DryArea
from evacuation.area_filter import AreaCandidate
from evacuation.evacuation_service import build_evacuation_response


class TestEvacuationService(unittest.TestCase):

    def setUp(self):
        self.area = DryArea(
            area_m2=20000,
            center_lat=12.9816,
            center_lon=77.5946,
            pixel_count=200,
        )

    def test_response_contains_destination(self):
        candidate = AreaCandidate(
            area=self.area,
            flood_fraction=0.0,
            building_fraction=0.05,
            eligible=True,
            reasons=[],
        )

        response = build_evacuation_response(
            user_lat=12.9716,
            user_lon=77.5946,
            candidates=[candidate],
        )

        self.assertEqual(len(response.destinations), 1)
        self.assertGreater(response.destinations[0].distance_m, 0)
        self.assertTrue(response.destinations[0].direction)
        self.assertEqual(
            response.destinations[0].verification_status,
            "unverified",
        )

    def test_ineligible_candidate_is_not_returned(self):
        candidate = AreaCandidate(
            area=self.area,
            flood_fraction=0.5,
            building_fraction=0.05,
            eligible=False,
            reasons=["Excessive flood exposure"],
        )

        response = build_evacuation_response(
            user_lat=12.9716,
            user_lon=77.5946,
            candidates=[candidate],
        )

        self.assertEqual(len(response.destinations), 0)


if __name__ == "__main__":
    unittest.main()
