"""Unit tests for DroneWatch domain data models."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from dronewatch.models.events import (
    AnalysisResult,
    BoundingBox,
    DroneStreamConfig,
    IncidentCategory,
    IncidentEvent,
    StreamStatus,
    ThreatLevel,
)


def test_bounding_box_valid() -> None:
    """Test valid BoundingBox instantiation."""
    bbox = BoundingBox(ymin=0.1, xmin=0.2, ymax=0.5, xmax=0.6, label="person")
    assert bbox.ymin == 0.1
    assert bbox.label == "person"


def test_bounding_box_out_of_bounds() -> None:
    """Test BoundingBox validates coordinate constraints."""
    with pytest.raises(ValidationError):
        BoundingBox(ymin=-0.5, xmin=0.0, ymax=1.5, xmax=1.0, label="vehicle")


def test_incident_event_serialization() -> None:
    """Test IncidentEvent serialization to dict and JSON."""
    event = IncidentEvent(
        event_id=uuid4(),
        drone_id="Drone-Alpha",
        threat_level=ThreatLevel.HIGH,
        category=IncidentCategory.PERIMETER_BREACH,
        description="Person climbing perimeter fence.",
        confidence_score=0.94,
    )
    assert event.drone_id == "Drone-Alpha"
    assert event.threat_level == ThreatLevel.HIGH
    assert event.acknowledged_by_pilot is False

    data = event.model_dump()
    assert data["drone_id"] == "Drone-Alpha"


def test_drone_stream_config_defaults() -> None:
    """Test DroneStreamConfig defaults."""
    config = DroneStreamConfig(
        drone_id="Drone-01",
        stream_url="rtsp://10.0.0.1/live",
        zone_name="Zone A",
    )
    assert config.status == StreamStatus.ONLINE
    assert config.fps == 30
    assert config.resolution == "1080p"


def test_analysis_result_validation() -> None:
    """Test AnalysisResult model validation."""
    result = AnalysisResult(
        suspicious_activity_detected=True,
        threat_level=ThreatLevel.CRITICAL,
        category=IncidentCategory.HAZARD,
        summary="Smoke detected near server building.",
        description="Dense smoke billowing near East wing HVAC system.",
        confidence_score=0.98,
        bounding_boxes=[BoundingBox(ymin=0.1, xmin=0.1, ymax=0.4, xmax=0.4, label="smoke")],
    )
    assert result.suspicious_activity_detected is True
    assert result.threat_level == ThreatLevel.CRITICAL
