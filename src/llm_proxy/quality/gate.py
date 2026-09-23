"""Local quality gate.

Thresholds were chosen before the first corpus measurement and are not
relaxed to obtain a pass. They are not official Alfa span-based scoring.
"""

MIN_F1 = 0.95
MIN_ROUND_TRIP_RATE = 1.0
MAX_NEGATIVE_DETECTIONS = 0
# First passing measurement, after correcting two handwritten occurrence indexes.
# Observed local F1 was 1.0 for every covered type and round-trip was 1.0.
# These observed values are not thresholds and are not official scoring.
BASELINE_FIXTURE_COUNT = 46
