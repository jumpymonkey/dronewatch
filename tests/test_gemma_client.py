"""Unit tests for Tier 1 Gemma 4 vision triage client and circuit breaker."""

from unittest.mock import patch

import httpx
import pytest

from dronewatch.config import Settings
from dronewatch.models.triage import GemmaTriageResponse
from dronewatch.services.gemma_client import GemmaTriageClient


@pytest.fixture
def gemma_settings() -> Settings:
    """Return Settings configured for Tier 1 Gemma 4 inference testing."""
    return Settings(
        enable_tier1_gemma=True,
        gemma_service_url="https://dronewatch-gemma-triage-test.a.run.app",
        gemma_model_name="google/gemma-4-E2B-it",
        gemma_triage_threshold=0.5,
        gemma_timeout_seconds=2.0,
        gemma_triage_prompt="detect campus security anomalies; answer safe or alert",
    )


@pytest.mark.parametrize(
    ("raw_text", "expected_alert", "min_score", "max_score", "expected_tag"),
    [
        ("safe", False, 0.0, 0.1, "safe"),
        ("normal campus pedestrian on walkway", False, 0.0, 0.1, "normal"),
        ("clear lawn with authorized groundskeeper", False, 0.0, 0.1, "clear"),
        ("alert: intruder spotted near building 4", True, 0.8, 1.0, "alert"),
        ("unauthorized vehicle parked on walkway", True, 0.8, 1.0, "unauthorized"),
        ("breach of north perimeter fence detected", True, 0.9, 1.0, "breach"),
        ("unknown blurry motion", False, 0.15, 0.25, "unclassified"),
    ],
)
def test_parse_triage_text_classifications(
    gemma_settings: Settings,
    raw_text: str,
    expected_alert: bool,
    min_score: float,
    max_score: float,
    expected_tag: str,
) -> None:
    """Test text parsing logic for zero-shot Gemma 4 responses."""
    client = GemmaTriageClient(gemma_settings)
    is_alert, score, tags = client._parse_triage_text(raw_text)

    assert is_alert == expected_alert
    assert min_score <= score <= max_score
    assert any(expected_tag in t for t in tags)


@pytest.mark.asyncio
async def test_triage_frame_benign_suppression(gemma_settings: Settings) -> None:
    """Verify benign Gemma 4 output suppresses Tier 2 Gemini escalation."""
    mock_response = {
        "id": "chatcmpl-test-benign",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "safe"},
                "finish_reason": "stop",
            }
        ],
    }

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/v1/chat/completions" in str(request.url)
        return httpx.Response(200, json=mock_response)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = GemmaTriageClient(gemma_settings, client=mock_http)
        result: GemmaTriageResponse = await client.triage_frame(
            frame_bytes=b"dummy_jpeg_bytes",
            drone_id="Drone-01",
        )

        assert not result.escalate_to_gemini
        assert not result.anomaly_detected
        assert result.tier1_decision == "BENIGN"
        assert result.triage_score < 0.5
        assert "safe" in result.tags


@pytest.mark.asyncio
async def test_triage_frame_scene_description_heartbeat(gemma_settings: Settings) -> None:
    """Verify scene description parsing and sanitization for routine 10s heartbeats."""
    mock_response = {
        "id": "chatcmpl-test-heartbeat",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Sunny campus perimeter with empty walkway. SAFE",
                },
                "finish_reason": "stop",
            }
        ],
    }

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/v1/chat/completions" in str(request.url)
        return httpx.Response(200, json=mock_response)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = GemmaTriageClient(gemma_settings, client=mock_http)
        result: GemmaTriageResponse = await client.triage_frame(
            frame_bytes=b"dummy_jpeg_bytes",
            drone_id="Drone-01",
            request_scene_description=True,
        )

        assert not result.escalate_to_gemini
        assert not result.anomaly_detected
        assert result.tier1_decision == "BENIGN"
        assert result.scene_description == "Sunny campus perimeter with empty walkway."
        assert "safe" in result.tags


@pytest.mark.asyncio
async def test_triage_frame_threat_escalation(gemma_settings: Settings) -> None:
    """Verify alert Gemma 4 output triggers Tier 2 Gemini escalation."""
    mock_response = {
        "id": "chatcmpl-test-alert",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "alert: unauthorized individual climbing perimeter fence",
                },
                "finish_reason": "stop",
            }
        ],
    }

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_response)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = GemmaTriageClient(gemma_settings, client=mock_http)
        result: GemmaTriageResponse = await client.triage_frame(
            frame_bytes=b"dummy_jpeg_bytes",
            drone_id="Drone-02",
        )

        assert result.escalate_to_gemini
        assert result.anomaly_detected
        assert result.tier1_decision in ("ANOMALOUS", "SUSPICIOUS")
        assert result.triage_score >= 0.8
        assert "alert" in result.tags or "unauthorized" in result.tags


@pytest.mark.asyncio
async def test_circuit_breaker_on_timeout(gemma_settings: Settings) -> None:
    """Verify circuit breaker fails open to Gemini when Tier 1 times out."""

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timed out after 2.0s")

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = GemmaTriageClient(gemma_settings, client=mock_http)
        result: GemmaTriageResponse = await client.triage_frame(
            frame_bytes=b"dummy_jpeg_bytes",
            drone_id="Drone-01",
        )

        # Must fail OPEN: escalate to Gemini to prevent security blind spots
        assert result.escalate_to_gemini
        assert result.tier1_decision == "CIRCUIT_BREAKER_BYPASS"
        assert "circuit_breaker_fail_open" in result.tags


@pytest.mark.asyncio
async def test_circuit_breaker_on_http_500(gemma_settings: Settings) -> None:
    """Verify circuit breaker fails open to Gemini when Tier 1 returns HTTP 500."""

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "CUDA OOM on L4 GPU"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = GemmaTriageClient(gemma_settings, client=mock_http)
        result: GemmaTriageResponse = await client.triage_frame(
            frame_bytes=b"dummy_jpeg_bytes",
            drone_id="Drone-01",
        )

        assert result.escalate_to_gemini
        assert result.tier1_decision == "CIRCUIT_BREAKER_BYPASS"
        assert "circuit_breaker_fail_open" in result.tags


@pytest.mark.asyncio
async def test_triage_bypasses_when_service_url_unset() -> None:
    """Verify unconfigured service URL immediately bypasses to Gemini."""
    settings = Settings(enable_tier1_gemma=True, gemma_service_url="")
    client = GemmaTriageClient(settings)
    result = await client.triage_frame(frame_bytes=b"dummy", drone_id="Drone-01")

    assert result.escalate_to_gemini
    assert result.tier1_decision == "CIRCUIT_BREAKER_BYPASS"
    assert "service_url_not_configured" in result.tags
    await client.aclose()


@pytest.mark.asyncio
async def test_oidc_token_header_injection(gemma_settings: Settings) -> None:
    """Verify Authorization Bearer header is added when OIDC token is acquired."""
    captured_auth: list[str] = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        auth_header = request.headers.get("Authorization", "")
        captured_auth.append(auth_header)
        return httpx.Response(200, json={"choices": [{"message": {"content": "safe"}}]})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = GemmaTriageClient(gemma_settings, client=mock_http)

        # Mock the internal token method to simulate valid GCP ID token
        with patch.object(client, "_get_oidc_token", return_value="mock-id-token-12345"):
            await client.triage_frame(frame_bytes=b"bytes", drone_id="Drone-01")

    assert len(captured_auth) == 1
    assert captured_auth[0] == "Bearer mock-id-token-12345"


@pytest.mark.asyncio
async def test_circuit_breaker_recovery(gemma_settings: Settings) -> None:
    """Verify circuit breaker logs recovery and resets flag on subsequent 200 OK."""
    call_count = 0

    async def flaky_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(500, text="Internal Server Error")
        return httpx.Response(200, json={"choices": [{"message": {"content": "SAFE"}}]})

    transport = httpx.MockTransport(flaky_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        client = GemmaTriageClient(gemma_settings, client=mock_http)

        # Call 1: fails, trips circuit breaker
        res1 = await client.triage_frame(frame_bytes=b"bytes", drone_id="Drone-01")
        assert res1.escalate_to_gemini
        assert client._circuit_tripped is True

        # Call 2: succeeds, resets circuit breaker
        res2 = await client.triage_frame(frame_bytes=b"bytes", drone_id="Drone-01")
        assert not res2.escalate_to_gemini
        assert client._circuit_tripped is False
