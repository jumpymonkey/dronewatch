"""Pydantic schemas and constants for dynamic image understanding workflow configuration."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_GEMMA_TRIAGE_PROMPT: str = (
    "detect campus security anomalies, unauthorized persons, perimeter breaches, "
    "or vehicles and equipment on pedestrian walkways; answer safe or alert"
)

DEFAULT_ALERT_KEYWORDS: tuple[str, ...] = (
    "alert",
    "suspicious",
    "anomalous",
    "anomaly",
    "intruder",
    "unauthorized",
    "trespass",
    "trespassing",
    "breach",
    "danger",
    "hazard",
    "threat",
    "weapon",
    "climbing",
    "fire",
    "smoke",
    "loitering",
    "equipment",
    "machinery",
    "vehicle",
    "cart",
    "lift",
    "crane",
    "obstruction",
    "blocked",
)

DEFAULT_BENIGN_KEYWORDS: tuple[str, ...] = (
    "safe",
    "normal",
    "benign",
    "clear",
    "empty",
    "routine",
    "authorized",
)

DEFAULT_GEMINI_ESCALATION_PROMPT: str = """\
Analyze this security video frame from a drone patrolling a 500-acre campus.
Identify suspicious campus behavior, security threats, safety hazards, or incidents including:
- Vehicles, cars, trucks, or equipment driving/parked on pedestrian paths, sidewalks, or lawns
- Heavy machinery, crane lifts, or construction equipment operating on sidewalks or walkways
- Perimeter fence breaches, climbing, or forced entry
- Loitering near restricted office buildings or parking garages after hours
- Unattended objects, bags, or suspicious packages in high-traffic pedestrian areas
- Traffic or parking violations in loading zones, fire lanes, or pedestrian zones
- Unauthorized human presence, trespassing, or safety hazards

Output strictly formatted JSON following this schema:
{
  "suspicious_activity_detected": boolean,
  "threat_level": "CLEAR" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "category": "CLEAR" | "PERIMETER_BREACH" | "LOITERING" | "UNATTENDED_OBJECT"
              | "TRAFFIC_VIOLATION" | "HAZARD" | "SUSPICIOUS_BEHAVIOR",
  "summary": "Short 1-sentence summary describing what is visible in the frame",
  "description": "Detailed observation description",
  "confidence_score": float (0.0 to 1.0),
  "bounding_boxes": [
    {
      "ymin": float (0.0 to 1.0),
      "xmin": float (0.0 to 1.0),
      "ymax": float (0.0 to 1.0),
      "xmax": float (0.0 to 1.0),
      "label": string
    }
  ]
}"""

DEFAULT_GEMMA_ESCALATION_PROMPT: str = DEFAULT_GEMINI_ESCALATION_PROMPT


class EscalationTarget(StrEnum):
    """Target inference model for escalated frame analysis."""

    GEMINI = "GEMINI"
    GEMMA = "GEMMA"


class AmbiguityPolicy(StrEnum):
    """Handling policy when front-line triage output is ambiguous or unclassified."""

    FAIL_SAFE = "FAIL_SAFE"
    CONSERVATIVE = "CONSERVATIVE"


class WorkflowConfig(BaseModel):
    """Complete active workflow configuration model."""

    model_config = ConfigDict(extra="forbid")

    enable_tier1_gemma: bool = Field(
        default=True,
        description="Whether Tier 1 Gemma triage is active before escalation",
    )
    gemma_triage_prompt: str = Field(
        default=DEFAULT_GEMMA_TRIAGE_PROMPT,
        description="Prompt guiding front-line Gemma 4 triage for SAFE vs ALERT verdict",
    )
    gemma_triage_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence cutoff above which a frame escalates",
    )
    escalation_target: EscalationTarget = Field(
        default=EscalationTarget.GEMINI,
        description="Target model for deep contextual analysis (GEMINI or GEMMA)",
    )
    gemini_escalation_prompt: str = Field(
        default=DEFAULT_GEMINI_ESCALATION_PROMPT,
        description="Detailed prompt used when escalating to Gemini Flash",
    )
    gemma_escalation_prompt: str = Field(
        default=DEFAULT_GEMMA_ESCALATION_PROMPT,
        description="Prompt used when escalating back to Gemma 4 for detailed reasoning",
    )
    gemini_model: str = Field(
        default="gemini-3.6-flash",
        description="Gemini model identifier",
    )
    gemma_model: str = Field(
        default="google/gemma-4-E2B-it",
        description="Gemma model identifier served by vLLM",
    )
    gemma_service_url: str | None = Field(
        default=None,
        description="Override internal Cloud Run / vLLM service URL",
    )
    gemma_timeout_seconds: float = Field(
        default=2.0,
        ge=0.5,
        le=30.0,
        description="HTTP timeout in seconds for Gemma triage/escalation calls",
    )
    alert_keywords: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALERT_KEYWORDS),
        description="Keywords triggering alert score in Gemma triage",
    )
    benign_keywords: list[str] = Field(
        default_factory=lambda: list(DEFAULT_BENIGN_KEYWORDS),
        description="Keywords indicating benign status in Gemma triage",
    )
    ambiguity_policy: AmbiguityPolicy = Field(
        default=AmbiguityPolicy.FAIL_SAFE,
        description="Handling policy when Gemma triage output is unclassified",
    )
    vllm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for vLLM inference",
    )
    vllm_max_tokens: int = Field(
        default=32,
        ge=8,
        le=512,
        description="Max tokens generated for front-line triage",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of last update in UTC",
    )
    updated_by: str = Field(
        default="pilot-admin",
        description="User or client who saved the configuration",
    )
    version: int = Field(default=1, ge=1, description="Configuration revision version number")

    @field_validator("escalation_target", mode="before")
    @classmethod
    def normalize_escalation_target(cls, v: object) -> object:
        """Coerce string enum input to uppercase."""
        if isinstance(v, str):
            return v.upper()
        return v

    @field_validator("ambiguity_policy", mode="before")
    @classmethod
    def normalize_ambiguity_policy(cls, v: object) -> object:
        """Coerce string enum input to uppercase."""
        if isinstance(v, str):
            return v.upper()
        return v


class WorkflowConfigUpdate(BaseModel):
    """Payload sent from Admin UI to update settings."""

    model_config = ConfigDict(extra="forbid")

    enable_tier1_gemma: bool | None = None
    gemma_triage_prompt: str | None = Field(default=None, min_length=5)
    gemma_triage_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    escalation_target: EscalationTarget | None = None
    gemini_escalation_prompt: str | None = Field(default=None, min_length=10)
    gemma_escalation_prompt: str | None = Field(default=None, min_length=10)
    gemini_model: str | None = Field(
        default=None, min_length=1, description="Gemini model identifier"
    )
    gemma_model: str | None = Field(
        default=None, min_length=1, description="Gemma model identifier served by vLLM"
    )
    gemma_service_url: str | None = None
    gemma_timeout_seconds: float | None = Field(default=None, ge=0.5, le=30.0)
    alert_keywords: list[str] | None = None
    benign_keywords: list[str] | None = None
    ambiguity_policy: AmbiguityPolicy | None = None
    vllm_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    vllm_max_tokens: int | None = Field(default=None, ge=8, le=512)

    @field_validator("escalation_target", mode="before")
    @classmethod
    def normalize_escalation_target(cls, v: object) -> object:
        """Coerce string enum input to uppercase."""
        if isinstance(v, str):
            return v.upper()
        return v

    @field_validator("ambiguity_policy", mode="before")
    @classmethod
    def normalize_ambiguity_policy(cls, v: object) -> object:
        """Coerce string enum input to uppercase."""
        if isinstance(v, str):
            return v.upper()
        return v
