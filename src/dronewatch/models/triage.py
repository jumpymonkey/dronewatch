"""Pydantic models for Tier 1 Gemma 4 vision triage service."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GemmaTriageRequest(BaseModel):
    """Payload sent to Tier 1 Gemma 4 inference service."""

    model_config = ConfigDict(extra="forbid")

    drone_id: str = Field(..., description="Unique drone identifier")
    frame_id: str = Field(..., description="Sequence or timestamp identifier for the frame")
    timestamp: datetime = Field(..., description="Frame acquisition timestamp in UTC")
    image_base64: str = Field(..., description="Base64 encoded JPEG/PNG frame payload")
    prompt: str = Field(
        default=(
            "detect campus security anomalies, unauthorized persons, "
            "or perimeter breaches; answer safe or alert"
        ),
        description="Zero-shot text prompt guiding front-line Gemma 4 triage",
    )


class GemmaTriageResponse(BaseModel):
    """Normalized response evaluated from Tier 1 Gemma 4 inference."""

    model_config = ConfigDict(extra="forbid")

    escalate_to_gemini: bool = Field(
        ...,
        description="True if frame warrants deep analysis by Tier 2 Gemini 3.6 Flash",
    )
    anomaly_detected: bool = Field(
        ...,
        description="True if anomalous or suspicious campus activity was spotted",
    )
    triage_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Calibrated threat confidence score from 0.0 (safe) to 1.0 (imminent danger)",
    )
    tier1_latency_ms: float = Field(
        ...,
        ge=0.0,
        description="Execution round-trip latency in milliseconds",
    )
    tier1_decision: Literal["BENIGN", "SUSPICIOUS", "ANOMALOUS", "CIRCUIT_BREAKER_BYPASS"] = Field(
        ...,
        description="Deterministic triage classification decision",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Keyword tags extracted from triage response",
    )
    raw_output: str | None = Field(
        default=None,
        description="Raw token output string returned by the model",
    )
    scene_description: str | None = Field(
        default=None,
        description="Concise natural language scene description from Gemma 4",
    )
    model_name: str | None = Field(
        default=None,
        description="Identifier of the serving model engine",
    )
