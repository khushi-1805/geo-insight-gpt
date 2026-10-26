"""
Valid-pixel confidence derived from SCL / polygon masking.

The analysis modules already compute a valid-pixel fraction.
This module converts that fraction into a percentage and a
High / Medium / Low label for the reporter and frontend.

Thresholds:
    High   >= 70% valid pixels
    Medium >= 40% and < 70%
    Low    <  40%
"""

LOW_CONFIDENCE_THRESHOLD = 40.0
HIGH_CONFIDENCE_THRESHOLD = 70.0


def valid_pixel_percentage(valid_fraction):
    """Convert a 0–1 fraction to a 0–100 percentage."""

    if valid_fraction is None:
        return None

    return float(round(float(valid_fraction) * 100.0, 2))


def confidence_level(valid_fraction=None, percentage=None):
    """
    Return 'high', 'medium', or 'low'.

    Pass either a 0–1 fraction or an already-computed percentage.
    """

    if percentage is None:
        percentage = valid_pixel_percentage(valid_fraction)

    if percentage is None:
        return None

    if percentage < LOW_CONFIDENCE_THRESHOLD:
        return "low"

    if percentage < HIGH_CONFIDENCE_THRESHOLD:
        return "medium"

    return "high"


def attach_confidence(valid_fraction):
    """Fields to merge into a yearly analysis result dict."""

    percentage = valid_pixel_percentage(valid_fraction)

    return {
        "valid_pixel_fraction": float(valid_fraction),
        "valid_pixel_percentage": percentage,
        "confidence": confidence_level(
            percentage=percentage
        )
    }


def is_low_confidence(percentage):
    if percentage is None:
        return False

    return float(percentage) < LOW_CONFIDENCE_THRESHOLD
