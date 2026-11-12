
import unittest

from evacuation.area_filter import AreaCandidate
from evacuation.destination_ranker import (
    calculate_bearing_degrees,
    compass_direction,
    haversine_distance_m,
    rank_destinations,
)
from evacuation.dry_area_detector import DryArea


def make_candidate(lat, lon, area_m2=20_000, eligible=True):
    area = DryArea(
        area_m2=area_m2,
        center_lat=lat,
        center_lon=lon,
        pixel_count=200,
    )
    return AreaCandidate(
        area=area,
        flood_fraction=0.0,
        building_fraction=0.0,
        eligible=eligible,
        reasons=[] if eligible else ["Not eligible"],
    )


class TestDestinationRanker(unittest.TestCase):

    def test_distance_is_zero_for_same_point(self):
        distance = haversine_distance_m(
            12.9716, 77.5946,
            12.9716, 77.5946,
        )
        self.assertAlmostEqual(distance, 0.0)

    def test_north_bearing(self):
        bearing = calculate_bearing_degrees(
            12.0, 77.0,
            13.0, 77.0,
        )
        self.assertAlmostEqual(bearing, 0.0, delta=0.1)
        self.assertEqual(compass_direction(bearing), "N")

    def test_east_bearing(self):
        bearing = calculate_bearing_degrees(
            12.0, 77.0,
            12.0, 78.0,
        )
        self.assertAlmostEqual(bearing, 90.0, delta=0.2)
        self.assertEqual(compass_direction(bearing), "E")

    def test_nearest_candidate_is_first(self):
        user_lat, user_lon = 12.9716, 77.5946

        nearby = make_candidate(12.9726, 77.5946)
        farther = make_candidate(12.9916, 77.5946)
        candidates = [farther, nearby]

        ranked = rank_destinations(
            candidates, user_lat, user_lon
        )

        self.assertEqual(len(ranked), 2)
        self.assertLess(
            ranked[0].distance_m,
            ranked[1].distance_m,
        )

    def test_ineligible_candidate_is_excluded(self):
        candidates = [
            make_candidate(12.9726, 77.5946, eligible=False),
            make_candidate(12.9916, 77.5946, eligible=True),
        ]

        ranked = rank_destinations(
            candidates, 12.9716, 77.5946
        )

        self.assertEqual(len(ranked), 1)
        self.assertGreater(ranked[0].distance_m, 0)

    def test_limit_is_respected(self):
        candidates = [
            make_candidate(12.9726, 77.5946),
            make_candidate(12.9816, 77.5946),
            make_candidate(12.9916, 77.5946),
        ]

        ranked = rank_destinations(
            candidates, 12.9716, 77.5946, limit=2
        )

        self.assertEqual(len(ranked), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
