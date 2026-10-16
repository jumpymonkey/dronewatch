"""Unit and integration tests for dynamic image understanding workflow configuration."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from dronewatch.config import Settings
from dronewatch.db.alloydb import AlloyDBManager
from dronewatch.main import app
from dronewatch.models.events import (
    AnalysisResult,
    DroneStreamConfig,
    IncidentCategory,
    IncidentEvent,
    StreamStatus,
    ThreatLevel,
)
from dronewatch.models.triage import GemmaTriageResponse
from dronewatch.models.workflow_config import (
    DEFAULT_GEMINI_ESCALATION_PROMPT,
    DEFAULT_GEMMA_ESCALATION_PROMPT,
    DEFAULT_GEMMA_TRIAGE_PROMPT,
    EscalationTarget,
    WorkflowConfig,
    WorkflowConfigUpdate,
)
from dronewatch.services.analyzer import GeminiVideoAnalyzer
from dronewatch.services.gemma_client import GemmaTriageClient
from dronewatch.services.stream_processor import DroneStreamProcessor

# ---------------------------------------------------------------------------
# 1. Pydantic Model Validation Tests
# ---------------------------------------------------------------------------


def test_workflow_config_defaults() -> None:
    """Verify default values match architectural specification."""
    config = WorkflowConfig()
    assert config.enable_tier1_gemma is True
    assert config.gemma_triage_prompt == DEFAULT_GEMMA_TRIAGE_PROMPT
    assert config.gemma_triage_threshold == 0.5
    assert config.escalation_target == EscalationTarget.GEMINI
    assert config.gemini_escalation_prompt == DEFAULT_GEMINI_ESCALATION_PROMPT
    assert config.gemma_escalation_prompt == DEFAULT_GEMMA_ESCALATION_PROMPT
    assert config.version == 1


def test_workflow_config_validation_threshold_bounds() -> None:
    """Verify threshold must be bounded within [0.0, 1.0]."""
    # Valid boundaries
    c_low = WorkflowConfig(gemma_triage_threshold=0.0)
    assert c_low.gemma_triage_threshold == 0.0

    c_high = WorkflowConfig(gemma_triage_threshold=1.0)
    assert c_high.gemma_triage_threshold == 1.0

    # Out of bounds
    with pytest.raises(ValidationError):
        WorkflowConfig(gemma_triage_threshold=-0.01)

    with pytest.raises(ValidationError):
        WorkflowConfig(gemma_triage_threshold=1.01)


def test_workflow_config_extra_forbidden() -> None:
    """Verify extra fields are strictly forbidden per coding standards."""
    with pytest.raises(ValidationError):
        WorkflowConfig.model_validate({"unknown_field": "disallowed"})

    with pytest.raises(ValidationError):
        WorkflowConfigUpdate.model_validate({"extra_field": 123})


def test_workflow_config_update_partial() -> None:
    """Verify partial updates allow modifying single fields and case normalization."""
    update = WorkflowConfigUpdate(
        escalation_target="gemma",  # type: ignore[arg-type]
        gemma_triage_threshold=0.75,
        gemini_model="gemini-3.8-flash",
    )
    dumped = update.model_dump(exclude_unset=True)
    assert dumped == {
        "escalation_target": EscalationTarget.GEMMA,
        "gemma_triage_threshold": 0.75,
        "gemini_model": "gemini-3.8-flash",
    }


# ---------------------------------------------------------------------------
# 2. AlloyDBManager Fallback Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_manager_workflow_config_lifecycle() -> None:
    """Verify get, save, and reset methods on AlloyDBManager in local fallback mode."""
    settings = Settings()
    db = AlloyDBManager(settings)

    # Initial default config
    cfg = await db.get_workflow_config()
    assert cfg.version == 1
    assert cfg.escalation_target == EscalationTarget.GEMINI

    # Save modified config (save increments version from 1 to 2)
    updated = cfg.model_copy(
        update={
            "escalation_target": EscalationTarget.GEMMA,
            "gemma_triage_threshold": 0.8,
        }
    )
    saved = await db.save_workflow_config(updated)
    assert saved.escalation_target == EscalationTarget.GEMMA
    assert saved.gemma_triage_threshold == 0.8
    assert saved.version == 2

    # Fetch again to verify persistence
    reloaded = await db.get_workflow_config()
    assert reloaded.escalation_target == EscalationTarget.GEMMA
    assert reloaded.gemma_triage_threshold == 0.8

    # Reset to defaults (increments version from 2 to 3)
    reset_cfg = await db.reset_workflow_config()
    assert reset_cfg.escalation_target == EscalationTarget.GEMINI
    assert reset_cfg.gemma_triage_threshold == 0.5
    assert reset_cfg.gemma_triage_prompt == DEFAULT_GEMMA_TRIAGE_PROMPT
    assert reset_cfg.version == 3


# ---------------------------------------------------------------------------
# 3. FastAPI REST Endpoints Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """Fixture returning FastAPI TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


def test_api_workflow_config_get(client: TestClient) -> None:
    """Test GET /api/admin/workflow-config returns active settings."""
    response = client.get("/api/admin/workflow-config")
    assert response.status_code == 200
    data = response.json()
    assert "enable_tier1_gemma" in data
    assert "escalation_target" in data
    assert "gemma_triage_prompt" in data
    assert "gemini_escalation_prompt" in data
    assert "gemma_escalation_prompt" in data


def test_api_workflow_config_put_and_reset(client: TestClient) -> None:
    """Test PUT /api/admin/workflow-config updates settings and POST reset restores defaults."""
    # Modify settings
    put_payload = {
        "escalation_target": "gemma",
        "gemma_triage_threshold": 0.65,
        "gemma_escalation_prompt": "Custom escalation prompt for Gemma 4 test.",
        "gemini_model": "gemini-3.8-flash",
    }
    put_resp = client.put("/api/admin/workflow-config", json=put_payload)
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["escalation_target"] == "GEMMA"
    assert data["gemma_triage_threshold"] == 0.65
    assert data["gemma_escalation_prompt"] == "Custom escalation prompt for Gemma 4 test."
    assert data["gemini_model"] == "gemini-3.8-flash"

    # Validate change persists on GET
    get_resp = client.get("/api/admin/workflow-config")
    assert get_resp.status_code == 200
    assert get_resp.json()["escalation_target"] == "GEMMA"
    assert get_resp.json()["gemini_model"] == "gemini-3.8-flash"

    # Reset
    reset_resp = client.post("/api/admin/workflow-config/reset")
    assert reset_resp.status_code == 200
    reset_data = reset_resp.json()
    assert reset_data["escalation_target"] == "GEMINI"
    assert reset_data["gemma_triage_threshold"] == 0.5
    assert reset_data["gemini_model"] == "gemini-3.6-flash"


def test_api_workflow_config_validation_rejection(client: TestClient) -> None:
    """Test PUT rejects out-of-range threshold or unexpected fields."""
    bad_payload = {"gemma_triage_threshold": 2.5}
    resp = client.put("/api/admin/workflow-config", json=bad_payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. StreamProcessor Dynamic Routing Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def test_stream_config() -> DroneStreamConfig:
    """Return test stream configuration."""
    return DroneStreamConfig(
        drone_id="Drone-Config-Routing-Test",
        stream_url="/dev/null",
        zone_name="Perimeter Test",
        status=StreamStatus.ONLINE,
    )


@pytest.mark.asyncio
async def test_stream_processor_routes_to_gemma_tier2(
    test_stream_config: DroneStreamConfig,
) -> None:
    """Verify processor routes Tier 2 escalation to Gemma 4 when configured."""
    custom_config = WorkflowConfig(
        enable_tier1_gemma=True,
        escalation_target=EscalationTarget.GEMMA,
        gemma_triage_prompt="Triage this alert carefully",
        gemma_triage_threshold=0.5,
        gemma_escalation_prompt="Perform deep inspection with Gemma",
    )

    async def mock_config_provider() -> WorkflowConfig:
        return custom_config

    mock_gemini = MagicMock(spec=GeminiVideoAnalyzer)
    mock_gemini.analyze_frame = AsyncMock()

    mock_gemma = MagicMock(spec=GemmaTriageClient)
    # Tier 1 triggers escalation
    mock_gemma.triage_frame = AsyncMock(
        return_value=GemmaTriageResponse(
            escalate_to_gemini=True,
            anomaly_detected=True,
            triage_score=0.85,
            tier1_latency_ms=45.0,
            tier1_decision="ANOMALOUS",
            scene_description="Intruder detected near fence",
        )
    )
    # Tier 2 Gemma escalation returns AnalysisResult
    mock_gemma.deep_analyze_frame = AsyncMock(
        return_value=AnalysisResult(
            threat_level=ThreatLevel.HIGH,
            category=IncidentCategory.PERIMETER_BREACH,
            summary="Gemma deep analysis: Person near fence",
            description="Person spotted in restricted perimeter.",
            confidence_score=0.88,
            bounding_boxes=[],
            suspicious_activity_detected=True,
        )
    )

    broadcast_mock = AsyncMock()
    processor = DroneStreamProcessor(
        config=test_stream_config,
        settings=Settings(),
        analyzer=mock_gemini,
        gemma_client=mock_gemma,
        config_provider=mock_config_provider,
        event_callback=broadcast_mock,
    )

    frame_bytes = b"fake-jpeg-bytes"
    await processor._analyze_frame(frame_bytes)

    # Assert Tier 1 received custom prompt and threshold
    mock_gemma.triage_frame.assert_awaited_once_with(
        frame_bytes=frame_bytes,
        drone_id="Drone-Config-Routing-Test",
        timestamp_sec=None,
        request_scene_description=False,
        prompt="Triage this alert carefully",
        threshold=0.5,
    )

    # Assert Tier 2 Gemma was called with custom prompt
    mock_gemma.deep_analyze_frame.assert_awaited_once_with(
        frame_bytes=frame_bytes,
        escalation_prompt="Perform deep inspection with Gemma",
        drone_id="Drone-Config-Routing-Test",
    )

    # Gemini was NOT called
    mock_gemini.analyze_frame.assert_not_awaited()

    # Incident was broadcast
    broadcast_mock.assert_awaited_once()
    event: IncidentEvent = broadcast_mock.call_args[0][0]
    assert event.threat_level == ThreatLevel.HIGH
    assert "Gemma deep analysis" in event.description


@pytest.mark.asyncio
async def test_stream_processor_tier1_disabled_calls_tier2_gemini(
    test_stream_config: DroneStreamConfig,
) -> None:
    """Verify processor bypasses Tier 1 when disabled and calls Gemini directly."""
    custom_config = WorkflowConfig(
        enable_tier1_gemma=False,
        escalation_target=EscalationTarget.GEMINI,
        gemini_escalation_prompt="Direct Gemini prompt without triage",
    )

    async def mock_config_provider() -> WorkflowConfig:
        return custom_config

    mock_gemini = MagicMock(spec=GeminiVideoAnalyzer)
    mock_gemini.analyze_frame = AsyncMock(
        return_value=AnalysisResult(
            threat_level=ThreatLevel.LOW,
            category=IncidentCategory.CLEAR,
            summary="Clear area",
            description="No threats detected.",
            confidence_score=0.95,
            bounding_boxes=[],
            suspicious_activity_detected=False,
        )
    )

    mock_gemma = MagicMock(spec=GemmaTriageClient)
    mock_gemma.triage_frame = AsyncMock()

    broadcast_mock = AsyncMock()
    processor = DroneStreamProcessor(
        config=test_stream_config,
        settings=Settings(),
        analyzer=mock_gemini,
        gemma_client=mock_gemma,
        config_provider=mock_config_provider,
        event_callback=broadcast_mock,
    )

    frame_bytes = b"fake-jpeg-bytes"
    await processor._analyze_frame(frame_bytes)

    # Tier 1 Gemma triage was completely bypassed
    mock_gemma.triage_frame.assert_not_awaited()

    # Gemini analyze_frame was called with custom prompt and model
    mock_gemini.analyze_frame.assert_awaited_once_with(
        image_bytes=frame_bytes,
        mime_type="image/jpeg",
        prompt="Direct Gemini prompt without triage",
        model="gemini-3.6-flash",
    )


@pytest.mark.parametrize(
    "target_model", ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-4-aragon"]
)
@pytest.mark.asyncio
async def test_stream_processor_uses_custom_gemini_model(
    test_stream_config: DroneStreamConfig,
    target_model: str,
) -> None:
    """Verify processor dynamically escalates to configured Gemini model."""
    custom_config = WorkflowConfig(
        enable_tier1_gemma=False,
        escalation_target=EscalationTarget.GEMINI,
        gemini_model=target_model,
        gemini_escalation_prompt="Escalation prompt for custom model",
    )

    mock_gemini = MagicMock(spec=GeminiVideoAnalyzer)
    mock_gemini.analyze_frame = AsyncMock(
        return_value=AnalysisResult(
            threat_level=ThreatLevel.LOW,
            category=IncidentCategory.CLEAR,
            summary="Zone clear",
            description="No suspicious activity.",
            confidence_score=0.9,
            bounding_boxes=[],
            suspicious_activity_detected=False,
            model_name=target_model,
        )
    )

    processor = DroneStreamProcessor(
        config=test_stream_config,
        settings=Settings(),
        analyzer=mock_gemini,
        config_provider=lambda: custom_config,
    )

    frame_bytes = b"test-frame-bytes"
    await processor._analyze_frame(frame_bytes)

    mock_gemini.analyze_frame.assert_awaited_once_with(
        image_bytes=frame_bytes,
        mime_type="image/jpeg",
        prompt="Escalation prompt for custom model",
        model=target_model,
    )


@pytest.mark.asyncio
async def test_analyzer_accepts_model_override() -> None:
    """Verify GeminiVideoAnalyzer invokes the overridden model when specified."""
    analyzer = GeminiVideoAnalyzer(Settings())
    mock_response = MagicMock()
    mock_response.text = (
        '{"threat_level": "CLEAR", "category": "CLEAR", "summary": "Clear", '
        '"description": "All good", "confidence_score": 0.95, "bounding_boxes": [], '
        '"suspicious_activity_detected": false}'
    )
    analyzer._sync_generate_content = MagicMock(return_value=mock_response)  # type: ignore[method-assign]

    result = await analyzer.analyze_frame(
        image_bytes=b"dummy-image",
        model="gemini-4-aragon",
    )
    assert result.model_name == "gemini-4-aragon"
    analyzer._sync_generate_content.assert_called_once()
    assert analyzer._sync_generate_content.call_args[0][0] == "gemini-4-aragon"
