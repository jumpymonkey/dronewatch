"""Unit tests for DroneStreamProcessor and timestamp formatting utilities."""

from dronewatch.services.stream_processor import format_video_timestamp


def test_format_video_timestamp_null_and_negative() -> None:
    """Test format_video_timestamp with None or invalid inputs."""
    assert format_video_timestamp(None) is None
    assert format_video_timestamp(-10.0) is None


def test_format_video_timestamp_minutes_seconds() -> None:
    """Test format_video_timestamp for under 1 hour."""
    assert format_video_timestamp(0.0) == "00:00"
    assert format_video_timestamp(45.2) == "00:45"
    assert format_video_timestamp(102.5) == "01:42"
    assert format_video_timestamp(599.9) == "09:59"


def test_format_video_timestamp_hours() -> None:
    """Test format_video_timestamp for over 1 hour."""
    assert format_video_timestamp(3600.0) == "01:00:00"
    assert format_video_timestamp(3665.2) == "01:01:05"
