"""Pydantic models for Tier 1 Gemma 4 System 1 decision triage service."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TriageVerdict(StrEnum):
    """Closed-set System 1 Choice primitive for front-line visual judgment."""

    SAFE = "SAFE"
    SUSPICIOUS = "SUSPICIOUS"
    CRITICAL = "CRITICAL"


class RoutingAction(StrEnum):
    """Deterministic control-plane routing actions owned by DecisionEngine."""

    SUPPRESS = "SUPPRESS"
    CORROBORATE_HOLD = "CORROBORATE_HOLD"
    ESCALATE_CORROBORATED = "ESCALATE_CORROBORATED"
    ESCALATE_IMMEDIATE = "ESCALATE_IMMEDIATE"
    COOLDOWN_SKIP = "COOLDOWN_SKIP"
    CIRCUIT_BREAKER_BYPASS = "CIRCUIT_BREAKER_BYPASS"


class DispatchAction(StrEnum):
    """Deterministic Tier 2 incident dispatch actions."""

    ACTIVE_ALERT = "ACTIVE_ALERT"
    SUPPRESSED_BELOW_POLICY = "SUPPRESSED_BELOW_POLICY"
    STALE_WATERMARK_DROPPED = "STALE_WATERMARK_DROPPED"
    CLEAR_ROUTINE = "CLEAR_ROUTINE"


class TriageClassProbabilities(BaseModel):
    """Calibrated probability distribution over System 1 Choice classes."""

    model_config = ConfigDict(extra="forbid")

    safe: float = Field(..., ge=0.0, le=1.0, description="Calibrated P(SAFE)")
    suspicious: float = Field(..., ge=0.0, le=1.0, description="Calibrated P(SUSPICIOUS)")
    critical: float = Field(..., ge=0.0, le=1.0, description="Calibrated P(CRITICAL)")
    entropy: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Normalized Shannon entropy [0.0=certain, 1.0=uniform uncertainty]",
    )
    calibrated_from_logprobs: bool = Field(
        default=False,
        description="True when derived from exact softmax over vLLM token logprobs",
    )


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
        description="True if frame meets static cutoff for Tier 2 evaluation",
    )
    anomaly_detected: bool = Field(
        ...,
        description="True if anomalous or suspicious campus activity was spotted",
    )
    triage_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Calibrated threat probability P(threat) = 1 - P(SAFE) in [0.0, 1.0]",
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
    verdict: TriageVerdict = Field(
        default=TriageVerdict.SAFE,
        description="Discrete System 1 Choice verdict (SAFE, SUSPICIOUS, CRITICAL)",
    )
    class_probabilities: TriageClassProbabilities | None = Field(
        default=None,
        description="Calibrated probability breakdown and uncertainty entropy",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Diagnostic tags extracted from triage evaluation",
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
