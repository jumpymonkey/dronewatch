"""Unit and integration tests for DroneWatch v3.0 System 1 Decision Framework."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import ValidationError

from dronewatch.config import Settings
from dronewatch.models.events import (
    AnalysisResult,
    DroneStreamConfig,
    IncidentCategory,
    IncidentEvent,
    ThreatLevel,
)
from dronewatch.models.triage import (
    DispatchAction,
    GemmaTriageResponse,
    RoutingAction,
    TriageVerdict,
)
from dronewatch.models.workflow_config import TriageMode, WorkflowConfig
from dronewatch.services.analyzer import GeminiVideoAnalyzer
from dronewatch.services.decision_engine import DecisionEngine
from dronewatch.services.gemma_client import GemmaTriageClient
from dronewatch.services.stream_processor import DroneStreamProcessor


@pytest.fixture
def gemma_settings() -> Settings:
    """Return Settings configured for Tier 1 System 1 decision testing."""
    return Settings(
        enable_tier1_gemma=True,
        triage_mode="DECISION_FRAMEWORK",
        gemma_service_url="https://dronewatch-gemma-triage-test.a.run.app",
        gemma_model_name="google/gemma-4-E2B-it",
        suppress_threshold=0.25,
        gemma_triage_threshold=0.65,
        corroboration_hits=2,
        corroboration_window=3,
        escalation_cooldown_seconds=3.0,
    )


# ---------------------------------------------------------------------------
# 1. vLLM Token Logprob Softmax Calibration & Entropy Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("top_logprobs", "expected_verdict", "min_p_threat", "max_p_threat", "min_entropy"),
    [
        (
            [
                {"token": "SAFE", "logprob": -0.02},
                {"token": "SUSPICIOUS", "logprob": -4.20},
                {"token": "CRITICAL", "logprob": -7.50},
            ],
            TriageVerdict.SAFE,
            0.0,
            0.05,
            0.0,
        ),
        (
            [
                {"token": "SAFE", "logprob": -0.60},
                {"token": "SUSPICIOUS", "logprob": -0.85},
                {"token": "CRITICAL", "logprob": -4.50},
            ],
            TriageVerdict.SUSPICIOUS,
            0.40,
            0.50,
            0.55,
        ),
        (
            [
                {"token": "CRITICAL", "logprob": -0.10},
                {"token": "SUSPICIOUS", "logprob": -2.40},
                {"token": "SAFE", "logprob": -6.00},
            ],
            TriageVerdict.CRITICAL,
            0.95,
            1.0,
            0.0,
        ),
    ],
)
def test_logprob_softmax_calibration_and_entropy(
    top_logprobs: list[dict[str, object]],
    expected_verdict: TriageVerdict,
    min_p_threat: float,
    max_p_threat: float,
    min_entropy: float,
) -> None:
    """Verify exact softmax calibration and Shannon entropy over vLLM top_logprobs."""
    choice_payload = {
        "index": 0,
        "message": {"role": "assistant", "content": str(top_logprobs[0]["token"])},
        "logprobs": {
            "content": [
                {
                    "token": str(top_logprobs[0]["token"]),
                    "logprob": top_logprobs[0]["logprob"],
                    "top_logprobs": top_logprobs,
                }
            ]
        },
    }

    calibrated = GemmaTriageClient._extract_logprob_calibration(choice_payload)
    assert calibrated is not None
    verdict, p_threat, probs = calibrated

    assert verdict == expected_verdict
    assert min_p_threat <= p_threat <= max_p_threat
    assert probs.calibrated_from_logprobs is True
    assert abs((probs.safe + probs.suspicious + probs.critical) - 1.0) < 1e-3
    assert probs.entropy >= min_entropy


@pytest.mark.asyncio
async def test_triage_frame_guided_choice_and_400_fallback(gemma_settings: Settings) -> None:
    """Verify client sends guided_choice + logprobs and retries cleanly on HTTP 400."""
    seen_payloads: list[dict[str, object]] = []

    async def mock_vllm(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.content.decode("utf-8"))
        seen_payloads.append(body)
        if "guided_choice" in body:
            return httpx.Response(400, json={"error": "guided_choice unsupported on legacy runner"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "SUSPICIOUS"},
                        "logprobs": {
                            "content": [
                                {
                                    "token": "SUSPICIOUS",
                                    "logprob": -0.70,
                                    "top_logprobs": [
                                        {"token": "SAFE", "logprob": -0.72},
                                        {"token": "SUSPICIOUS", "logprob": -0.70},
                                        {"token": "CRITICAL", "logprob": -5.0},
                                    ],
                                }
                            ]
                        },
                    }
                ]
            },
        )

    transport = httpx.MockTransport(mock_vllm)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = GemmaTriageClient(gemma_settings, client=http_client)
        res = await client.triage_frame(frame_bytes=b"jpeg", drone_id="Drone-01")

    assert len(seen_payloads) == 2
    assert seen_payloads[0].get("guided_choice") == ["SAFE", "SUSPICIOUS", "CRITICAL"]
    assert seen_payloads[0].get("logprobs") is True
    assert "guided_choice" not in seen_payloads[1]
    assert res.class_probabilities is not None
    assert res.class_probabilities.calibrated_from_logprobs is True
    assert 0.48 <= res.triage_score <= 0.55


@pytest.mark.parametrize(
    "negated_sentence",
    [
        "No equipment blocking the walkway; area is safe.",
        "Walkway is clear without unauthorized vehicles or hazards.",
        "Zero intruders and no perimeter breach detected.",
    ],
)
def test_negation_safe_triage_fallback(gemma_settings: Settings, negated_sentence: str) -> None:
    """Verify negated alert keywords never trigger false-positive escalations."""
    client = GemmaTriageClient(gemma_settings)
    is_alert, score, _tags = client._parse_triage_text(negated_sentence)
    assert is_alert is False
    assert score <= 0.10


def test_contrastive_clause_after_negation_still_alerts(gemma_settings: Settings) -> None:
    """Verify negation does not swallow threats after contrastive 'but'."""
    client = GemmaTriageClient(gemma_settings)
    is_alert, score, tags = client._parse_triage_text(
        "No equipment on north walkway, but intruder climbing south fence."
    )
    assert is_alert is True
    assert score >= 0.90
    assert "intruder" in tags or "climbing" in tags


# ---------------------------------------------------------------------------
# 2. Deterministic 3-Band Routing & Non-Blocking Temporal Corroboration
# ---------------------------------------------------------------------------


def _make_triage(
    score: float,
    verdict: TriageVerdict = TriageVerdict.SUSPICIOUS,
    decision: str = "SUSPICIOUS",
) -> GemmaTriageResponse:
    return GemmaTriageResponse(
        escalate_to_gemini=score >= 0.65,
        anomaly_detected=score >= 0.25,
        triage_score=score,
        tier1_latency_ms=19.5,
        tier1_decision=decision,  # type: ignore[arg-type]
        verdict=verdict,
        tags=[verdict.value.lower()],
    )


def test_decision_engine_3band_corroboration_lifecycle() -> None:
    """Verify Band 0 suppress, Band 1 k-of-n hold/escalate, and TTL expiry."""
    engine = DecisionEngine(corroboration_ttl_seconds=4.5)
    cfg = WorkflowConfig(
        suppress_threshold=0.25,
        gemma_triage_threshold=0.65,
        corroboration_hits=2,
        corroboration_window=3,
        escalation_cooldown_seconds=0.0,
    )

    # 1. Band 0 (0.08 < 0.25): Immediate SUPPRESS
    d0 = engine.evaluate_tier1(
        "Drone-A", _make_triage(0.08, TriageVerdict.SAFE, "BENIGN"), cfg, now_wall=10.0
    )
    assert d0.action == RoutingAction.SUPPRESS
    assert d0.should_escalate is False

    # 2. Band 1 Frame #1 (0.42 in [0.25, 0.65)): CORROBORATE_HOLD (1/2)
    d1 = engine.evaluate_tier1("Drone-A", _make_triage(0.42), cfg, now_wall=11.0)
    assert d1.action == RoutingAction.CORROBORATE_HOLD
    assert d1.should_escalate is False
    assert d1.window_hits == 1

    # 3. Band 0 intervening frame (0.10) does not erase hit within 3-frame window
    d_safe = engine.evaluate_tier1(
        "Drone-A", _make_triage(0.10, TriageVerdict.SAFE, "BENIGN"), cfg, now_wall=12.0
    )
    assert d_safe.action == RoutingAction.SUPPRESS
    assert d_safe.window_hits == 1

    # 4. Band 1 Frame #2 (0.48) within 3-frame window -> ESCALATE_CORROBORATED (2/2)!
    d2 = engine.evaluate_tier1("Drone-A", _make_triage(0.48), cfg, now_wall=13.0)
    assert d2.action == RoutingAction.ESCALATE_CORROBORATED
    assert d2.should_escalate is True

    # 5. Stale Band 1 observation expires after TTL (4.5s) -> does not false-corroborate
    d_isolated = engine.evaluate_tier1("Drone-A", _make_triage(0.40), cfg, now_wall=20.0)
    assert d_isolated.action == RoutingAction.CORROBORATE_HOLD
    d_after_ttl = engine.evaluate_tier1("Drone-A", _make_triage(0.40), cfg, now_wall=26.0)
    assert d_after_ttl.action == RoutingAction.CORROBORATE_HOLD
    assert d_after_ttl.window_hits == 1


# ---------------------------------------------------------------------------
# 3. Anti-Snowball Single-Flight, Cooldown & Critical Override Tests
# ---------------------------------------------------------------------------


def test_anti_snowball_single_flight_and_cooldown_with_critical_override() -> None:
    """Verify duplicate escalations are shed while in-flight/cooldown unless CRITICAL."""
    engine = DecisionEngine()
    cfg = WorkflowConfig(
        suppress_threshold=0.25,
        gemma_triage_threshold=0.60,
        escalation_cooldown_seconds=3.0,
    )

    # Frame 1 (Band 2: 0.75) escalates immediately
    r1 = engine.evaluate_tier1("Drone-B", _make_triage(0.75), cfg, now_wall=100.0)
    assert r1.action == RoutingAction.ESCALATE_IMMEDIATE
    assert r1.should_escalate is True

    # Tier 2 starts (single-flight lock active)
    engine.mark_tier2_started("Drone-B")
    r_inflight = engine.evaluate_tier1("Drone-B", _make_triage(0.78), cfg, now_wall=100.5)
    assert r_inflight.action == RoutingAction.COOLDOWN_SKIP
    assert r_inflight.should_escalate is False
    assert "single_flight" in r_inflight.reason

    # Tier 2 finishes at t=101.0 -> 3.0s cooldown armed until t=104.0
    engine.mark_tier2_finished("Drone-B", record_cooldown=True, now_wall=101.0)
    r_cool = engine.evaluate_tier1("Drone-B", _make_triage(0.72), cfg, now_wall=102.5)
    assert r_cool.action == RoutingAction.COOLDOWN_SKIP
    assert r_cool.should_escalate is False
    assert "cooldown" in r_cool.reason

    # CRITICAL verdict overrides cooldown immediately!
    r_crit = engine.evaluate_tier1(
        "Drone-B",
        _make_triage(0.96, verdict=TriageVerdict.CRITICAL, decision="ANOMALOUS"),
        cfg,
        now_wall=102.8,
    )
    assert r_crit.action == RoutingAction.ESCALATE_IMMEDIATE
    assert r_crit.should_escalate is True

    # After cooldown expires (t=104.5), normal Band 2 escalations resume
    r_resumed = engine.evaluate_tier1("Drone-B", _make_triage(0.70), cfg, now_wall=104.5)
    assert r_resumed.action == RoutingAction.ESCALATE_IMMEDIATE
    assert r_resumed.should_escalate is True


# ---------------------------------------------------------------------------
# 4. Decoupled Tier 2 Dispatch Policy & Monotonic Watermark Tests
# ---------------------------------------------------------------------------


def test_decoupled_dispatch_threshold_and_monotonic_watermark() -> None:
    """Verify Tier 2 dispatch uses decoupled threshold and drops stale out-of-order frames."""
    engine = DecisionEngine()
    cfg = WorkflowConfig(
        suppress_threshold=0.20,
        gemma_triage_threshold=0.45,
        dispatch_confidence_threshold=0.80,
    )

    medium_alert = AnalysisResult(
        suspicious_activity_detected=True,
        threat_level=ThreatLevel.MEDIUM,
        category=IncidentCategory.LOITERING,
        summary="Person near loading dock",
        description="Person standing near dock.",
        confidence_score=0.68,
        bounding_boxes=[],
    )

    # Confidence 0.68 >= gemma_triage_threshold (0.45) BUT < dispatch_confidence_threshold (0.80)
    disp1 = engine.evaluate_tier2_dispatch("Drone-C", medium_alert, cfg, video_timestamp_sec=12.0)
    assert disp1.action == DispatchAction.SUPPRESSED_BELOW_POLICY
    assert disp1.trigger_alert is False

    # Newer frame at TC 14.0s arrives with high confidence 0.88 -> ACTIVE_ALERT
    high_alert = medium_alert.model_copy(update={"confidence_score": 0.88})
    disp2 = engine.evaluate_tier2_dispatch("Drone-C", high_alert, cfg, video_timestamp_sec=14.0)
    assert disp2.action == DispatchAction.ACTIVE_ALERT
    assert disp2.trigger_alert is True

    # Slow out-of-order frame from TC 13.0s finishes late -> STALE_WATERMARK_DROPPED
    disp_stale = engine.evaluate_tier2_dispatch(
        "Drone-C", medium_alert, cfg, video_timestamp_sec=13.0
    )
    assert disp_stale.action == DispatchAction.STALE_WATERMARK_DROPPED
    assert disp_stale.trigger_alert is False


def test_workflow_config_rejects_invalid_corroboration_bounds() -> None:
    """Verify corroboration_hits > corroboration_window raises ValidationError."""
    with pytest.raises(ValidationError):
        WorkflowConfig(corroboration_hits=4, corroboration_window=3)


@pytest.mark.asyncio
async def test_stream_processor_end_to_end_corroboration_to_gemini() -> None:
    """Verify StreamProcessor holds first Band 1 frame and escalates second to Gemini."""
    wf = WorkflowConfig(
        enable_tier1_gemma=True,
        triage_mode=TriageMode.DECISION_FRAMEWORK,
        suppress_threshold=0.25,
        gemma_triage_threshold=0.65,
        dispatch_confidence_threshold=0.75,
        corroboration_hits=2,
        corroboration_window=3,
        escalation_cooldown_seconds=3.0,
    )

    mock_gemma = MagicMock(spec=GemmaTriageClient)
    mock_gemma.triage_frame = AsyncMock(
        side_effect=[
            _make_triage(0.45),  # Frame 1: Band 1 -> Hold
            _make_triage(0.52),  # Frame 2: Band 1 -> Corroborated Escalate!
        ]
    )

    mock_gemini = MagicMock(spec=GeminiVideoAnalyzer)
    mock_gemini.analyze_frame = AsyncMock(
        return_value=AnalysisResult(
            suspicious_activity_detected=True,
            threat_level=ThreatLevel.MEDIUM,
            category=IncidentCategory.HAZARD,
            summary="Forklift obstructing pedestrian sidewalk.",
            description="Forklift parked across north pedestrian walkway.",
            confidence_score=0.86,
            bounding_boxes=[],
        )
    )

    emitted: list[IncidentEvent] = []

    async def capture(ev: IncidentEvent) -> None:
        emitted.append(ev)

    proc = DroneStreamProcessor(
        config=DroneStreamConfig(
            drone_id="Drone-E2E",
            stream_url="/dev/null",
            zone_name="North Walkway",
        ),
        settings=Settings(enable_tier1_gemma=True),
        analyzer=mock_gemini,
        gemma_client=mock_gemma,
        event_callback=capture,
        config_provider=lambda: wf,
    )

    # Frame 1 at t=1.0s: held in O(1) ring buffer without calling Gemini
    await proc._analyze_frame(b"frame-1", video_timestamp_sec=1.0)
    mock_gemini.analyze_frame.assert_not_called()
    assert len(emitted) == 0

    # Frame 2 at t=2.0s: 2/3 corroborated -> escalates to Gemini and dispatches alert
    await proc._analyze_frame(b"frame-2", video_timestamp_sec=2.0)
    mock_gemini.analyze_frame.assert_called_once()
    assert len(emitted) == 1
    assert emitted[0].routing_action == str(RoutingAction.ESCALATE_CORROBORATED)
    assert emitted[0].dispatch_action == str(DispatchAction.ACTIVE_ALERT)
    assert emitted[0].threat_level == ThreatLevel.MEDIUM
