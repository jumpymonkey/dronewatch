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
            "Evaluate this campus security drone frame. Classify into exactly one label:\n"
            "- SAFE: Normal routine campus scene, empty area, or authorized walkway use.\n"
            "- SUSPICIOUS: Ambiguous motion, unattended object, loitering, "
            "or walkway obstruction.\n"
            "- CRITICAL: Active perimeter breach, intruder climbing, weapon, fire, "
            "or imminent danger.\n"
            "Respond with one word only: SAFE, SUSPICIOUS, or CRITICAL."
        ),
        description="System 1 Choice rubric prompt guiding front-line Gemma 4 triage",
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


class DecisionTelemetryEvent(BaseModel):
    """Real-time System 1 Decision Engine telemetry broadcast per evaluated frame."""

    model_config = ConfigDict(extra="forbid")

    event_type: Literal["decision_telemetry"] = Field(
        default="decision_telemetry",
        description="Discriminator distinguishing System 1 telemetry from IncidentEvent",
    )
    drone_id: str = Field(..., description="Reporting drone identifier")
    timestamp: datetime = Field(..., description="UTC timestamp of decision evaluation")
    video_timestamp_formatted: str | None = Field(
        default=None, description="Formatted video timecode e.g. 02:42"
    )
    triage_mode: Literal["DECISION_FRAMEWORK"] = Field(
        default="DECISION_FRAMEWORK",
        description="Active Tier 1 System 1 triage mode (DECISION_FRAMEWORK)",
    )
    model_name: str | None = Field(default=None, description="Tier 1 serving model identifier")
    verdict: TriageVerdict = Field(default=TriageVerdict.SAFE, description="System 1 choice token")
    p_threat: float = Field(..., ge=0.0, le=1.0, description="Calibrated P(threat)")
    p_safe: float = Field(default=1.0, ge=0.0, le=1.0, description="Calibrated P(SAFE)")
    p_suspicious: float = Field(default=0.0, ge=0.0, le=1.0, description="Calibrated P(SUSPICIOUS)")
    p_critical: float = Field(default=0.0, ge=0.0, le=1.0, description="Calibrated P(CRITICAL)")
    entropy: float = Field(default=0.0, ge=0.0, le=1.0, description="Normalized Shannon entropy")
    calibrated_from_logprobs: bool = Field(
        default=False, description="True when calibrated from exact vLLM top_logprobs"
    )
    routing_action: str = Field(..., description="Tier 1 RoutingAction")
    dispatch_action: str | None = Field(
        default=None, description="Optional Tier 2 DispatchAction once escalation completes"
    )
    reason: str = Field(..., description="Deterministic audit reason for decision")
    window_hits: int = Field(default=0, ge=0, description="Active Band 1+ hits in ring buffer")
    window_size: int = Field(default=0, ge=0, description="Current ring buffer occupancy")
    corroboration_hits_required: int = Field(
        default=2, ge=1, description="Configured k hits required to corroborate"
    )
    corroboration_window_capacity: int = Field(
        default=3, ge=1, description="Configured n window capacity"
    )
    suppress_threshold: float = Field(default=0.25, ge=0.0, le=1.0, description="Band 0 ceiling")
    escalate_threshold: float = Field(default=0.50, ge=0.0, le=1.0, description="Band 2 cutoff")
    latency_ms: float = Field(default=0.0, ge=0.0, description="Tier 1 latency in milliseconds")
    raw_output: str | None = Field(default=None, description="Raw model token output")
    counts: dict[str, int] = Field(
        default_factory=dict,
        description="Cumulative per-stream decision counters",
    )
