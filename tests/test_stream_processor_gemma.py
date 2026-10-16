"""Integration tests verifying two-tier triage interaction in DroneStreamProcessor."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dronewatch.config import Settings
from dronewatch.models.events import (
    AnalysisResult,
    DroneStreamConfig,
    IncidentCategory,
    IncidentEvent,
    StreamStatus,
    ThreatLevel,
)
from dronewatch.models.triage import GemmaTriageResponse
from dronewatch.models.workflow_config import EscalationTarget, WorkflowConfig
from dronewatch.services.analyzer import GeminiVideoAnalyzer
from dronewatch.services.gemma_client import GemmaTriageClient
from dronewatch.services.stream_processor import DroneStreamProcessor


@pytest.fixture
def stream_config() -> DroneStreamConfig:
    """Return test stream configuration."""
    return DroneStreamConfig(
        drone_id="Drone-Test-01",
        stream_url="/dev/null",
        zone_name="Perimeter Gate Alpha",
        status=StreamStatus.ONLINE,
    )


@pytest.fixture
def tier1_enabled_settings() -> Settings:
    """Return Settings with Tier 1 Gemma 4 triage enabled."""
    return Settings(
        enable_tier1_gemma=True,
        gemma_service_url="https://mock-gemma-run.a.run.app",
        gemma_triage_threshold=0.5,
    )


@pytest.fixture
def tier1_disabled_settings() -> Settings:
    """Return Settings with Tier 1 Gemma 4 triage disabled."""
    return Settings(enable_tier1_gemma=False)


@pytest.fixture
def mock_gemini_analyzer() -> MagicMock:
    """Return mock GeminiVideoAnalyzer returning a high-threat incident."""
    analyzer = MagicMock(spec=GeminiVideoAnalyzer)
    analyzer.analyze_frame = AsyncMock(
        return_value=AnalysisResult(
            threat_level=ThreatLevel.HIGH,
            category=IncidentCategory.PERIMETER_BREACH,
            summary="Perimeter fence cut detected",
            description="Person with wire cutters observed penetrating perimeter barrier.",
            confidence_score=0.92,
            bounding_boxes=[
                {"ymin": 0.1, "xmin": 0.1, "ymax": 0.3, "xmax": 0.3, "label": "intruder"}
            ],
            suspicious_activity_detected=True,
        )
    )
    return analyzer


@pytest.mark.asyncio
async def test_tier1_suppresses_benign_frame(
    stream_config: DroneStreamConfig,
    tier1_enabled_settings: Settings,
    mock_gemini_analyzer: MagicMock,
) -> None:
    """Verify benign frame classified by Tier 1 stops before invoking Gemini."""
    mock_gemma = MagicMock(spec=GemmaTriageClient)
    mock_gemma.triage_frame = AsyncMock(
        return_value=GemmaTriageResponse(
            escalate_to_gemini=False,
            anomaly_detected=False,
            triage_score=0.04,
            tier1_latency_ms=38.5,
            tier1_decision="BENIGN",
            tags=["safe", "routine"],
        )
    )

    callback_events: list[IncidentEvent] = []

    async def mock_callback(event: IncidentEvent) -> None:
        callback_events.append(event)

    processor = DroneStreamProcessor(
        config=stream_config,
        settings=tier1_enabled_settings,
        analyzer=mock_gemini_analyzer,
        gemma_client=mock_gemma,
        event_callback=mock_callback,
    )

    dummy_frame = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    await processor._analyze_frame(
        frame_bytes_data=dummy_frame,
        video_timestamp_sec=15.0,
        is_heartbeat=False,
    )

    # Gemini analyzer must NEVER be called for routine benign frames
    mock_gemini_analyzer.analyze_frame.assert_not_called()
    assert len(callback_events) == 0


@pytest.mark.asyncio
async def test_tier1_benign_heartbeat_emits_clear_event_without_gemini(
    stream_config: DroneStreamConfig,
    tier1_enabled_settings: Settings,
    mock_gemini_analyzer: MagicMock,
) -> None:
    """Verify 10s heartbeat emits clear telemetry event without calling Gemini."""
    mock_gemma = MagicMock(spec=GemmaTriageClient)
    mock_gemma.triage_frame = AsyncMock(
        return_value=GemmaTriageResponse(
            escalate_to_gemini=False,
            anomaly_detected=False,
            triage_score=0.05,
            tier1_latency_ms=42.0,
            tier1_decision="BENIGN",
            tags=["safe"],
            scene_description="Sunny campus lawn with clear walkway.",
        )
    )

    callback_events: list[IncidentEvent] = []

    async def mock_callback(event: IncidentEvent) -> None:
        callback_events.append(event)

    processor = DroneStreamProcessor(
        config=stream_config,
        settings=tier1_enabled_settings,
        analyzer=mock_gemini_analyzer,
        gemma_client=mock_gemma,
        event_callback=mock_callback,
    )

    dummy_frame = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    await processor._analyze_frame(
        frame_bytes_data=dummy_frame,
        video_timestamp_sec=10.0,
        is_heartbeat=True,
    )

    # Gemini must NOT be called for benign heartbeat
    mock_gemini_analyzer.analyze_frame.assert_not_called()

    # Event callback must receive routine CLEAR event with scene description
    assert len(callback_events) == 1
    event = callback_events[0]
    assert event.threat_level == ThreatLevel.NONE
    assert event.category == IncidentCategory.CLEAR
    assert "Sunny campus lawn with clear walkway." in event.description
    assert event.video_timestamp_seconds == 10.0


@pytest.mark.asyncio
async def test_tier1_escalates_suspicious_frame(
    stream_config: DroneStreamConfig,
    tier1_enabled_settings: Settings,
    mock_gemini_analyzer: MagicMock,
) -> None:
    """Verify suspicious frame escalated by Tier 1 reaches Gemini and triggers dispatch."""
    mock_gemma = MagicMock(spec=GemmaTriageClient)
    mock_gemma.triage_frame = AsyncMock(
        return_value=GemmaTriageResponse(
            escalate_to_gemini=True,
            anomaly_detected=True,
            triage_score=0.88,
            tier1_latency_ms=44.1,
            tier1_decision="ANOMALOUS",
            tags=["breach", "fence"],
        )
    )

    callback_events: list[IncidentEvent] = []

    async def mock_callback(event: IncidentEvent) -> None:
        callback_events.append(event)

    processor = DroneStreamProcessor(
        config=stream_config,
        settings=tier1_enabled_settings,
        analyzer=mock_gemini_analyzer,
        gemma_client=mock_gemma,
        event_callback=mock_callback,
    )

    dummy_frame = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    await processor._analyze_frame(
        frame_bytes_data=dummy_frame,
        video_timestamp_sec=30.0,
        is_heartbeat=False,
    )

    # Escalates to Gemini
    mock_gemini_analyzer.analyze_frame.assert_called_once()
    assert len(callback_events) == 1
    assert callback_events[0].threat_level == ThreatLevel.HIGH


@pytest.mark.asyncio
async def test_circuit_breaker_fails_open_to_gemini(
    stream_config: DroneStreamConfig,
    tier1_enabled_settings: Settings,
    mock_gemini_analyzer: MagicMock,
) -> None:
    """Verify that when Tier 1 fails, circuit breaker trips open to preserve safety."""
    mock_gemma = MagicMock(spec=GemmaTriageClient)
    mock_gemma.triage_frame = AsyncMock(
        return_value=GemmaTriageResponse(
            escalate_to_gemini=True,
            anomaly_detected=True,
            triage_score=1.0,
            tier1_latency_ms=2001.0,
            tier1_decision="CIRCUIT_BREAKER_BYPASS",
            tags=["circuit_breaker_fail_open"],
        )
    )

    callback_events: list[IncidentEvent] = []

    async def mock_callback(event: IncidentEvent) -> None:
        callback_events.append(event)

    processor = DroneStreamProcessor(
        config=stream_config,
        settings=tier1_enabled_settings,
        analyzer=mock_gemini_analyzer,
        gemma_client=mock_gemma,
        event_callback=mock_callback,
    )

    dummy_frame = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    await processor._analyze_frame(
        frame_bytes_data=dummy_frame,
        video_timestamp_sec=45.0,
        is_heartbeat=False,
    )

    # Gemini called despite Tier 1 failure
    mock_gemini_analyzer.analyze_frame.assert_called_once()
    assert len(callback_events) == 1
    assert callback_events[0].threat_level == ThreatLevel.HIGH


@pytest.mark.asyncio
async def test_tier2_gemma_without_tier1_clear_frame(
    stream_config: DroneStreamConfig,
    tier1_disabled_settings: Settings,
    mock_gemini_analyzer: MagicMock,
) -> None:
    """Verify that when Tier 1 is disabled and Gemma is Tier 2, clear frames do not alert."""
    mock_gemma = MagicMock(spec=GemmaTriageClient)
    mock_gemma.deep_analyze_frame = AsyncMock(
        return_value=AnalysisResult(
            suspicious_activity_detected=False,
            threat_level=ThreatLevel.NONE,
            category=IncidentCategory.CLEAR,
            summary="Routine aerial surveillance - zone clear.",
            description="No suspicious activity detected.",
            confidence_score=0.95,
            bounding_boxes=[],
        )
    )

    callback_events: list[IncidentEvent] = []

    async def mock_callback(event: IncidentEvent) -> None:
        callback_events.append(event)

    wf_config = WorkflowConfig(
        enable_tier1_gemma=False,
        escalation_target=EscalationTarget.GEMMA,
        gemma_triage_threshold=0.70,
    )

    processor = DroneStreamProcessor(
        config=stream_config,
        settings=tier1_disabled_settings,
        analyzer=mock_gemini_analyzer,
        gemma_client=mock_gemma,
        event_callback=mock_callback,
        config_provider=lambda: wf_config,
    )

    dummy_frame = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    await processor._analyze_frame(frame_bytes_data=dummy_frame, video_timestamp_sec=10.0)

    # Gemini must not be called; Gemma deep analyze was called
    mock_gemini_analyzer.analyze_frame.assert_not_called()
    mock_gemma.deep_analyze_frame.assert_called_once()

    # Must stay online, not in ALERT
    assert processor.config.status == StreamStatus.ONLINE
    assert len(callback_events) == 1
    assert callback_events[0].threat_level == ThreatLevel.NONE
    assert callback_events[0].category == IncidentCategory.CLEAR


@pytest.mark.asyncio
async def test_tier2_gemma_without_tier1_below_threshold_suppressed(
    stream_config: DroneStreamConfig,
    tier1_disabled_settings: Settings,
    mock_gemini_analyzer: MagicMock,
) -> None:
    """Verify that a potential threat below threshold is suppressed to ONLINE and NONE threat."""
    mock_gemma = MagicMock(spec=GemmaTriageClient)
    # Gemma reports low confidence anomaly 0.60, while threshold is 0.75
    mock_gemma.deep_analyze_frame = AsyncMock(
        return_value=AnalysisResult(
            suspicious_activity_detected=True,
            threat_level=ThreatLevel.LOW,
            category=IncidentCategory.SUSPICIOUS_BEHAVIOR,
            summary="Ambiguous shadow near walkway",
            description="Ambiguous shadow near walkway",
            confidence_score=0.60,
            bounding_boxes=[],
        )
    )

    callback_events: list[IncidentEvent] = []

    async def mock_callback(event: IncidentEvent) -> None:
        callback_events.append(event)

    wf_config = WorkflowConfig(
        enable_tier1_gemma=False,
        escalation_target=EscalationTarget.GEMMA,
        gemma_triage_threshold=0.75,
    )

    processor = DroneStreamProcessor(
        config=stream_config,
        settings=tier1_disabled_settings,
        analyzer=mock_gemini_analyzer,
        gemma_client=mock_gemma,
        event_callback=mock_callback,
        config_provider=lambda: wf_config,
    )

    dummy_frame = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    await processor._analyze_frame(frame_bytes_data=dummy_frame, video_timestamp_sec=12.0)

    # Suppressed below threshold
    assert processor.config.status == StreamStatus.ONLINE
    assert len(callback_events) == 1
    assert callback_events[0].threat_level == ThreatLevel.NONE
    assert callback_events[0].category == IncidentCategory.CLEAR


@pytest.mark.asyncio
async def test_tier2_gemma_without_tier1_above_threshold_alerts(
    stream_config: DroneStreamConfig,
    tier1_disabled_settings: Settings,
    mock_gemini_analyzer: MagicMock,
) -> None:
    """Verify that a threat meeting or exceeding threshold triggers ALERT status and event."""
    mock_gemma = MagicMock(spec=GemmaTriageClient)
    mock_gemma.deep_analyze_frame = AsyncMock(
        return_value=AnalysisResult(
            suspicious_activity_detected=True,
            threat_level=ThreatLevel.HIGH,
            category=IncidentCategory.PERIMETER_BREACH,
            summary="Fence breach detected",
            description="Person breaching security fence.",
            confidence_score=0.88,
            bounding_boxes=[
                {"ymin": 0.1, "xmin": 0.1, "ymax": 0.4, "xmax": 0.4, "label": "trespasser"}
            ],
        )
    )

    callback_events: list[IncidentEvent] = []

    async def mock_callback(event: IncidentEvent) -> None:
        callback_events.append(event)

    wf_config = WorkflowConfig(
        enable_tier1_gemma=False,
        escalation_target=EscalationTarget.GEMMA,
        gemma_triage_threshold=0.70,
    )

    processor = DroneStreamProcessor(
        config=stream_config,
        settings=tier1_disabled_settings,
        analyzer=mock_gemini_analyzer,
        gemma_client=mock_gemma,
        event_callback=mock_callback,
        config_provider=lambda: wf_config,
    )

    dummy_frame = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    await processor._analyze_frame(frame_bytes_data=dummy_frame, video_timestamp_sec=14.0)

    # Dispatched alert
    assert processor.config.status == StreamStatus.ALERT
    assert len(callback_events) == 1
    assert callback_events[0].threat_level == ThreatLevel.HIGH
    assert callback_events[0].category == IncidentCategory.PERIMETER_BREACH
    assert len(callback_events[0].bounding_boxes) == 1
