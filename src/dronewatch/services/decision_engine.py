"""Deterministic System 1 Decision Framework & Anti-Snowball Control Plane."""

import time
from collections import deque
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from dronewatch.models.events import AnalysisResult, ThreatLevel
from dronewatch.models.triage import (
    DispatchAction,
    GemmaTriageResponse,
    RoutingAction,
    TriageVerdict,
)
from dronewatch.models.workflow_config import WorkflowConfig

# Maximum wall-clock age for Band 1 frames in the temporal corroboration ring buffer
DEFAULT_CORROBORATION_TTL_SECONDS: float = 4.5


@dataclass(slots=True)
class FrameObservation:
    """Single non-blocking Tier 1 observation stored in per-stream ring buffer."""

    wall_time: float
    video_time: float | None
    p_threat: float
    is_band1_or_higher: bool


@dataclass
class StreamDecisionState:
    """Mutable O(1) decision and anti-snowball state isolated per drone stream."""

    observations: deque[FrameObservation] = field(default_factory=deque)
    tier2_in_flight: bool = False
    last_escalation_wall_time: float = -1000.0
    latest_tier2_frame_ts: float = -1.0
    suppressed_count: int = 0
    corroborate_hold_count: int = 0
    escalated_count: int = 0
    cooldown_skip_count: int = 0
    stale_dropped_count: int = 0
    policy_suppressed_count: int = 0
    active_alert_count: int = 0


class RoutingDecision(BaseModel):
    """Typed control-plane decision emitted after Tier 1 System 1 judgment."""

    model_config = ConfigDict(extra="forbid")

    action: RoutingAction = Field(..., description="Selected Tier 1 routing action")
    should_escalate: bool = Field(
        ..., description="True when frame is cleared to invoke Tier 2 reasoning"
    )
    reason: str = Field(..., description="Audit rationale for routing transition")
    p_threat: float = Field(..., ge=0.0, le=1.0, description="Evaluated P(threat)")
    suppress_cutoff: float = Field(..., ge=0.0, le=1.0, description="Active Band 0 ceiling")
    escalate_cutoff: float = Field(..., ge=0.0, le=1.0, description="Active Band 2 cutoff")
    window_hits: int = Field(default=0, ge=0, description="Active Band 1+ hits in sliding window")
    window_size: int = Field(default=0, ge=0, description="Current sliding window occupancy")


class DispatchDecision(BaseModel):
    """Typed dispatch decision emitted after Tier 2 contextual evaluation."""

    model_config = ConfigDict(extra="forbid")

    action: DispatchAction = Field(..., description="Selected Tier 2 dispatch action")
    trigger_alert: bool = Field(
        ..., description="True if stream enters ALERT and persists incident to AlloyDB"
    )
    effective_threshold: float = Field(
        ..., ge=0.0, le=1.0, description="Evaluated dispatch confidence threshold"
    )
    reason: str = Field(..., description="Audit rationale for dispatch transition")


class DecisionEngine:
    """Code-owned deterministic decision router and anti-snowball gatekeeper.

    Implements a 3-band System 1 routing topology:
    - Band 0 (SUPPRESS): P(threat) < suppress_threshold -> immediate drop.
    - Band 1 (CORROBORATE): suppress_threshold <= P(threat) < gemma_triage_threshold ->
      O(1) non-blocking ring-buffer check requiring k-of-n hits within TTL.
    - Band 2 (ESCALATE_IMMEDIATE): P(threat) >= gemma_triage_threshold or CRITICAL ->
      immediate escalation gated by single-flight and cooldown anti-snowball guards.
    """

    def __init__(
        self, corroboration_ttl_seconds: float = DEFAULT_CORROBORATION_TTL_SECONDS
    ) -> None:
        """Initialize decision engine with empty per-stream state registry."""
        self.corroboration_ttl_seconds: float = corroboration_ttl_seconds
        self._states: dict[str, StreamDecisionState] = {}

    def get_state(self, drone_id: str) -> StreamDecisionState:
        """Return or initialize isolated decision state for a drone stream."""
        state = self._states.get(drone_id)
        if state is None:
            state = StreamDecisionState()
            self._states[drone_id] = state
        return state

    def reset_stream(self, drone_id: str) -> None:
        """Clear accumulated temporal state for a stopped or reset stream."""
        self._states.pop(drone_id, None)

    def get_counts_snapshot(self, drone_id: str) -> dict[str, int]:
        """Return cumulative System 1 & Tier 2 decision counters for a stream."""
        state = self.get_state(drone_id)
        total_tier1 = (
            state.suppressed_count
            + state.corroborate_hold_count
            + state.escalated_count
            + state.cooldown_skip_count
        )
        return {
            "total_evaluated": total_tier1,
            "suppressed": state.suppressed_count,
            "corroborate_hold": state.corroborate_hold_count,
            "escalated": state.escalated_count,
            "cooldown_skip": state.cooldown_skip_count,
            "stale_dropped": state.stale_dropped_count,
            "policy_suppressed": state.policy_suppressed_count,
            "active_alerts": state.active_alert_count,
        }

    def _prune_and_record(
        self,
        state: StreamDecisionState,
        obs: FrameObservation,
        window_capacity: int,
    ) -> None:
        """Prune expired observations, handle MP4 loop resets, and append in O(1)."""
        # Detect looped MP4 playback (video timestamp jumped backward > 2s)
        if (
            obs.video_time is not None
            and state.observations
            and state.observations[-1].video_time is not None
            and obs.video_time < state.observations[-1].video_time - 2.0
        ):
            state.observations.clear()

        cutoff_wall = obs.wall_time - self.corroboration_ttl_seconds
        while state.observations and state.observations[0].wall_time < cutoff_wall:
            state.observations.popleft()

        while len(state.observations) >= window_capacity:
            state.observations.popleft()

        state.observations.append(obs)

    def _is_critical_override(self, triage: GemmaTriageResponse) -> bool:
        """Return True if frame indicates imminent critical threat bypassing cooldown."""
        if triage.verdict == TriageVerdict.CRITICAL:
            return True
        if triage.class_probabilities and triage.class_probabilities.critical >= 0.50:
            return True
        return triage.triage_score >= 0.93

    def _check_anti_snowball_gate(
        self,
        state: StreamDecisionState,
        triage: GemmaTriageResponse,
        config: WorkflowConfig,
        now_wall: float,
    ) -> str | None:
        """Return block reason if single-flight or cooldown gate sheds Tier 2 load."""
        is_critical = self._is_critical_override(triage)
        if state.tier2_in_flight and not is_critical:
            return "tier2_single_flight_active"

        elapsed = now_wall - state.last_escalation_wall_time
        if (
            config.escalation_cooldown_seconds > 0.0
            and elapsed < config.escalation_cooldown_seconds
            and not is_critical
        ):
            return (
                f"escalation_cooldown_active "
                f"({elapsed:.1f}s < {config.escalation_cooldown_seconds:.1f}s)"
            )

        return None

    def evaluate_tier1(
        self,
        drone_id: str,
        triage: GemmaTriageResponse,
        config: WorkflowConfig,
        video_timestamp_sec: float | None = None,
        now_wall: float | None = None,
    ) -> RoutingDecision:
        """Evaluate Tier 1 judgment against deterministic 3-band routing rules."""
        wall = now_wall if now_wall is not None else time.monotonic()
        state = self.get_state(drone_id)

        escalate_cutoff = config.gemma_triage_threshold
        suppress_cutoff = min(config.suppress_threshold, escalate_cutoff)
        p_threat = triage.triage_score

        # 0. Circuit breaker fail-open path
        if triage.tier1_decision == "CIRCUIT_BREAKER_BYPASS":
            if state.tier2_in_flight:
                state.cooldown_skip_count += 1
                return RoutingDecision(
                    action=RoutingAction.COOLDOWN_SKIP,
                    should_escalate=False,
                    reason="circuit_breaker_single_flight_active",
                    p_threat=p_threat,
                    suppress_cutoff=suppress_cutoff,
                    escalate_cutoff=escalate_cutoff,
                    window_hits=0,
                    window_size=len(state.observations),
                )
            state.escalated_count += 1
            return RoutingDecision(
                action=RoutingAction.CIRCUIT_BREAKER_BYPASS,
                should_escalate=True,
                reason="tier1_circuit_breaker_fail_open",
                p_threat=p_threat,
                suppress_cutoff=suppress_cutoff,
                escalate_cutoff=escalate_cutoff,
                window_hits=1,
                window_size=len(state.observations),
            )

        is_band2 = p_threat >= escalate_cutoff or triage.verdict == TriageVerdict.CRITICAL
        is_band0 = p_threat < suppress_cutoff and not is_band2

        # 1. Band 0: Immediate deterministic suppression
        if is_band0:
            self._prune_and_record(
                state,
                FrameObservation(
                    wall_time=wall,
                    video_time=video_timestamp_sec,
                    p_threat=p_threat,
                    is_band1_or_higher=False,
                ),
                window_capacity=config.corroboration_window,
            )
            hits = sum(1 for o in state.observations if o.is_band1_or_higher)
            state.suppressed_count += 1
            return RoutingDecision(
                action=RoutingAction.SUPPRESS,
                should_escalate=False,
                reason="below_suppress_threshold",
                p_threat=p_threat,
                suppress_cutoff=suppress_cutoff,
                escalate_cutoff=escalate_cutoff,
                window_hits=hits,
                window_size=len(state.observations),
            )

        # Record Band 1 / Band 2 observation in non-blocking ring buffer
        self._prune_and_record(
            state,
            FrameObservation(
                wall_time=wall,
                video_time=video_timestamp_sec,
                p_threat=p_threat,
                is_band1_or_higher=True,
            ),
            window_capacity=config.corroboration_window,
        )
        hits = sum(1 for o in state.observations if o.is_band1_or_higher)
        win_len = len(state.observations)

        # 2. Band 2: Immediate escalation candidate
        if is_band2:
            shed_reason = self._check_anti_snowball_gate(state, triage, config, wall)
            if shed_reason is not None:
                state.cooldown_skip_count += 1
                return RoutingDecision(
                    action=RoutingAction.COOLDOWN_SKIP,
                    should_escalate=False,
                    reason=shed_reason,
                    p_threat=p_threat,
                    suppress_cutoff=suppress_cutoff,
                    escalate_cutoff=escalate_cutoff,
                    window_hits=hits,
                    window_size=win_len,
                )
            state.escalated_count += 1
            return RoutingDecision(
                action=RoutingAction.ESCALATE_IMMEDIATE,
                should_escalate=True,
                reason="band2_immediate_threshold_met",
                p_threat=p_threat,
                suppress_cutoff=suppress_cutoff,
                escalate_cutoff=escalate_cutoff,
                window_hits=hits,
                window_size=win_len,
            )

        # 3. Band 1: Ambiguous band -> require k-of-n temporal corroboration
        if hits < config.corroboration_hits:
            state.corroborate_hold_count += 1
            return RoutingDecision(
                action=RoutingAction.CORROBORATE_HOLD,
                should_escalate=False,
                reason=f"awaiting_temporal_corroboration ({hits}/{config.corroboration_hits})",
                p_threat=p_threat,
                suppress_cutoff=suppress_cutoff,
                escalate_cutoff=escalate_cutoff,
                window_hits=hits,
                window_size=win_len,
            )

        shed_reason = self._check_anti_snowball_gate(state, triage, config, wall)
        if shed_reason is not None:
            state.cooldown_skip_count += 1
            return RoutingDecision(
                action=RoutingAction.COOLDOWN_SKIP,
                should_escalate=False,
                reason=shed_reason,
                p_threat=p_threat,
                suppress_cutoff=suppress_cutoff,
                escalate_cutoff=escalate_cutoff,
                window_hits=hits,
                window_size=win_len,
            )

        # Clear corroborated buffer once promoted to Tier 2 so subsequent waves corroborate cleanly
        state.observations.clear()
        state.escalated_count += 1
        return RoutingDecision(
            action=RoutingAction.ESCALATE_CORROBORATED,
            should_escalate=True,
            reason=f"temporal_corroboration_met ({hits}/{config.corroboration_hits})",
            p_threat=p_threat,
            suppress_cutoff=suppress_cutoff,
            escalate_cutoff=escalate_cutoff,
            window_hits=hits,
            window_size=win_len,
        )

    def mark_tier2_started(self, drone_id: str) -> None:
        """Acquire single-flight lock before dispatching async Tier 2 inference."""
        state = self.get_state(drone_id)
        state.tier2_in_flight = True

    def mark_tier2_finished(
        self,
        drone_id: str,
        record_cooldown: bool = True,
        now_wall: float | None = None,
    ) -> None:
        """Release single-flight lock and arm anti-snowball cooldown timer."""
        state = self.get_state(drone_id)
        state.tier2_in_flight = False
        if record_cooldown:
            state.last_escalation_wall_time = now_wall if now_wall is not None else time.monotonic()

    def evaluate_tier2_dispatch(
        self,
        drone_id: str,
        analysis: AnalysisResult,
        config: WorkflowConfig,
        video_timestamp_sec: float | None = None,
    ) -> DispatchDecision:
        """Evaluate Tier 2 AnalysisResult against decoupled campus-wide dispatch policy."""
        state = self.get_state(drone_id)
        base_cutoff = config.effective_dispatch_threshold

        # Monotonic video watermark guard against out-of-order Tier 2 completions
        if video_timestamp_sec is not None:
            if state.latest_tier2_frame_ts >= 0.0:
                # Reset watermark if video file looped back to beginning
                if video_timestamp_sec < state.latest_tier2_frame_ts - 5.0:
                    state.latest_tier2_frame_ts = video_timestamp_sec
                elif video_timestamp_sec < state.latest_tier2_frame_ts:
                    state.stale_dropped_count += 1
                    return DispatchDecision(
                        action=DispatchAction.STALE_WATERMARK_DROPPED,
                        trigger_alert=False,
                        effective_threshold=base_cutoff,
                        reason=(
                            f"stale_frame_dropped ({video_timestamp_sec:.2f}s < "
                            f"{state.latest_tier2_frame_ts:.2f}s)"
                        ),
                    )
                else:
                    state.latest_tier2_frame_ts = video_timestamp_sec
            else:
                state.latest_tier2_frame_ts = video_timestamp_sec

        is_potential_threat = (
            analysis.suspicious_activity_detected or analysis.threat_level != ThreatLevel.NONE
        )
        if not is_potential_threat:
            return DispatchDecision(
                action=DispatchAction.CLEAR_ROUTINE,
                trigger_alert=False,
                effective_threshold=base_cutoff,
                reason="tier2_classified_clear",
            )

        # Severity-modulated cutoff when explicit dispatch_confidence_threshold is configured
        effective_cutoff = base_cutoff
        if (
            config.dispatch_confidence_threshold is not None
            and analysis.threat_level == ThreatLevel.CRITICAL
        ):
            effective_cutoff = round(base_cutoff * 0.90, 4)

        if analysis.confidence_score >= effective_cutoff:
            state.active_alert_count += 1
            return DispatchDecision(
                action=DispatchAction.ACTIVE_ALERT,
                trigger_alert=True,
                effective_threshold=effective_cutoff,
                reason=(
                    f"policy_matched ({analysis.threat_level} "
                    f"conf={analysis.confidence_score:.2f} >= {effective_cutoff:.2f})"
                ),
            )

        state.policy_suppressed_count += 1
        return DispatchDecision(
            action=DispatchAction.SUPPRESSED_BELOW_POLICY,
            trigger_alert=False,
            effective_threshold=effective_cutoff,
            reason=(
                f"confidence_below_dispatch_policy "
                f"({analysis.confidence_score:.2f} < {effective_cutoff:.2f})"
            ),
        )
