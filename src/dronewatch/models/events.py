"""Domain data models and Pydantic schemas for DroneWatch."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ThreatLevel(StrEnum):
    """Threat severity levels for security alerts."""

    NONE = "CLEAR"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentCategory(StrEnum):
    """Categorization of detected campus incidents."""

    CLEAR = "CLEAR"
    PERIMETER_BREACH = "PERIMETER_BREACH"
    LOITERING = "LOITERING"
    UNATTENDED_OBJECT = "UNATTENDED_OBJECT"
    TRAFFIC_VIOLATION = "TRAFFIC_VIOLATION"
    HAZARD = "HAZARD"
    SUSPICIOUS_BEHAVIOR = "SUSPICIOUS_BEHAVIOR"


class StreamStatus(StrEnum):
    """Status of drone RTSP / MP4 video streams."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ALERT = "ALERT"


class BoundingBox(BaseModel):
    """Normalized bounding box coordinates (0.0 to 1.0) for detected objects."""

    model_config = ConfigDict(extra="forbid")

    ymin: float = Field(..., ge=0.0, le=1.0, description="Top Y coordinate ratio")
    xmin: float = Field(..., ge=0.0, le=1.0, description="Left X coordinate ratio")
    ymax: float = Field(..., ge=0.0, le=1.0, description="Bottom Y coordinate ratio")
    xmax: float = Field(..., ge=0.0, le=1.0, description="Right X coordinate ratio")
    label: str = Field(
        default="detected_object", description="Object class label e.g., person, vehicle, bag"
    )


class Location(BaseModel):
    """GPS location and campus zone metadata for drone telemetry."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(default=37.7749, description="Latitude degree")
    longitude: float = Field(default=-122.4194, description="Longitude degree")
    altitude_meters: float = Field(default=45.0, description="Drone altitude in meters")
    zone_name: str = Field(default="North Perimeter Gate 3", description="Named campus zone")


class IncidentEvent(BaseModel):
    """Pydantic model representing a logged security incident event."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4, description="Unique incident event ID")
    drone_id: str = Field(..., description="Identifier of reporting drone")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    location: Location = Field(default_factory=Location, description="Location metadata")
    threat_level: ThreatLevel = Field(..., description="Severity threat level")
    category: IncidentCategory = Field(..., description="Incident category classification")
    description: str = Field(..., description="Detailed visual analysis description from Gemini")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    bounding_boxes: list[BoundingBox] = Field(
        default_factory=list, description="Detected object bounding boxes"
    )
    snapshot_uri: str | None = Field(
        default=None, description="GCS URI or local path to frame snapshot image"
    )
    video_timestamp_seconds: float | None = Field(
        default=None, description="Video stream timestamp in seconds when event occurred"
    )
    video_timestamp_formatted: str | None = Field(
        default=None, description="Formatted video playback timestamp e.g. 01:42"
    )
    acknowledged_by_pilot: bool = Field(
        default=False, description="Whether pilot has acknowledged alert"
    )


class DroneStreamConfig(BaseModel):
    """Configuration for an active drone video stream."""

    model_config = ConfigDict(extra="forbid")

    drone_id: str = Field(..., description="Unique drone callsign or ID")
    stream_url: str = Field(..., description="RTSP URL or gs:// MP4 file URI")
    zone_name: str = Field(..., description="Assigned patrol zone")
    status: StreamStatus = Field(default=StreamStatus.ONLINE, description="Stream state")
    fps: int = Field(default=30, description="Stream frame rate")
    resolution: str = Field(default="1080p", description="Stream resolution e.g., 1080p, 4K")


class AnalysisResult(BaseModel):
    """Structured response schema for Gemini 3.6 Flash multimodal outputs."""

    model_config = ConfigDict(extra="forbid")

    suspicious_activity_detected: bool = Field(
        ..., description="True if any suspicious behavior is spotted"
    )
    threat_level: ThreatLevel = Field(..., description="Assessed threat level")
    category: IncidentCategory = Field(..., description="Primary category of event")
    summary: str = Field(..., description="Short summary of visual scene")
    description: str = Field(..., description="Detailed natural language observation")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence ratio")
    bounding_boxes: list[BoundingBox] = Field(
        default_factory=list, description="Target bounding boxes"
    )
    raw_payload: dict[str, Any] = Field(default_factory=dict, description="Metadata key-values")
