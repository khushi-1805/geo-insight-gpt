import os
import tempfile
import unittest

import numpy as np

from confidence import (
    LOW_CONFIDENCE_THRESHOLD,
    attach_confidence,
    confidence_level,
    is_low_confidence,
    valid_pixel_percentage,
)
from analysis.overlay import colorize_index, write_png


class ConfidenceTests(unittest.TestCase):

    def test_percentage_from_fraction(self):

        self.assertEqual(
            valid_pixel_percentage(0.8321),
            83.21
        )

    def test_high_medium_low(self):

        self.assertEqual(
            confidence_level(valid_fraction=0.91),
            "high"
        )

        self.assertEqual(
            confidence_level(valid_fraction=0.55),
            "medium"
        )

        self.assertEqual(
            confidence_level(valid_fraction=0.2),
            "low"
        )

    def test_low_confidence_threshold(self):

        self.assertTrue(
            is_low_confidence(
                LOW_CONFIDENCE_THRESHOLD - 0.1
            )
        )

        self.assertFalse(
            is_low_confidence(70)
        )

    def test_attach_confidence_fields(self):

        fields = attach_confidence(0.61)

        self.assertEqual(
            fields["valid_pixel_percentage"],
            61.0
        )

        self.assertEqual(
            fields["confidence"],
            "medium"
        )

        self.assertAlmostEqual(
            fields["valid_pixel_fraction"],
            0.61
        )


class OverlayTests(unittest.TestCase):

    def test_colorize_makes_rgba_and_hides_nan(self):

        values = np.array(
            [
                [0.8, np.nan],
                [0.0, 0.4]
            ],
            dtype=float
        )

        rgba = colorize_index(
            values,
            colormap="ndvi"
        )

        self.assertEqual(
            rgba.shape,
            (2, 2, 4)
        )

        self.assertEqual(
            int(rgba[0, 1, 3]),
            0
        )

        self.assertGreater(
            int(rgba[0, 0, 3]),
            0
        )

    def test_png_roundtrip_header(self):

        rgba = colorize_index(
            np.array(
                [[0.1, 0.9], [0.3, 0.6]],
                dtype=float
            ),
            colormap="ndvi"
        )

        with tempfile.TemporaryDirectory() as folder:

            path = os.path.join(
                folder,
                "test.png"
            )

            write_png(path, rgba)

            header = open(path, "rb").read(8)

            self.assertEqual(
                header,
                b"\x89PNG\r\n\x1a\n"
            )


if __name__ == "__main__":

    unittest.main()
