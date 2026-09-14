"""Unit tests for OpenCV MotionFilter service."""

import numpy as np

from dronewatch.services.motion_filter import MotionFilter


def test_motion_filter_first_frame_baseline() -> None:
    """Test first frame establishes baseline and reports true."""
    filter = MotionFilter(sensitivity_threshold=15.0, min_motion_area=100)
    frame1 = np.zeros((480, 640, 3), dtype=np.uint8)

    has_motion, score = filter.process_frame(frame1)
    assert has_motion is True
    assert score == 1.0


def test_motion_filter_identical_frames() -> None:
    """Test subsequent identical static frames yield no motion."""
    filter = MotionFilter(sensitivity_threshold=15.0, min_motion_area=100)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # First frame initializes baseline
    filter.process_frame(frame)

    # Second identical frame should report no motion
    has_motion, score = filter.process_frame(frame)
    assert has_motion is False
    assert score == 0.0


def test_motion_filter_detects_significant_motion() -> None:
    """Test motion filter detects added bright box in frame."""
    filter = MotionFilter(sensitivity_threshold=15.0, min_motion_area=100)
    frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
    filter.process_frame(frame1)

    # Introduce large white rectangle in second frame
    frame2 = np.zeros((480, 640, 3), dtype=np.uint8)
    frame2[100:300, 100:300] = 255

    has_motion, score = filter.process_frame(frame2)
    assert has_motion is True
    assert score > 0.0
