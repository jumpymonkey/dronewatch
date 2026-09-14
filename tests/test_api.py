"""Integration tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient

from dronewatch.main import app


@pytest.fixture
def client() -> TestClient:
    """Fixture returning FastAPI TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


def test_health_check_endpoint(client: TestClient) -> None:
    """Test /health endpoint returns HTTP 200 and expected payload."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "gemini_model" in data


def test_list_streams_endpoint(client: TestClient) -> None:
    """Test GET /api/streams returns list of active streams."""
    response = client.get("/api/streams")
    assert response.status_code == 200
    streams = response.json()
    assert isinstance(streams, list)
    assert len(streams) >= 1


def test_register_and_unregister_stream_endpoint(client: TestClient) -> None:
    """Test POST /api/streams to register and DELETE /api/streams/{drone_id} to unregister."""
    payload = {
        "drone_id": "Drone-Test-Registration",
        "stream_url": "/home/jeffleinen/jeffdev/dronevideos/videos/S1002353.MP4",
        "zone_name": "Test Zone",
    }
    # Register stream
    reg_response = client.post("/api/streams", json=payload)
    assert reg_response.status_code == 200
    reg_data = reg_response.json()
    assert reg_data["drone_id"] == "Drone-Test-Registration"

    # Test GET /api/streams/{drone_id}/video
    video_response = client.get(
        "/api/streams/Drone-Test-Registration/video", follow_redirects=False
    )
    assert video_response.status_code in (200, 307)

    # Unregister stream
    del_response = client.delete("/api/streams/Drone-Test-Registration")
    assert del_response.status_code == 200
    del_data = del_response.json()
    assert del_data["status"] == "success"
    assert del_data["drone_id"] == "Drone-Test-Registration"


def test_trigger_simulated_alert_endpoint(client: TestClient) -> None:
    """Test POST /api/simulation/trigger creates and returns alert."""
    payload = {
        "drone_id": "Drone-Test",
        "threat_level": "HIGH",
        "category": "PERIMETER_BREACH",
        "description": "Simulated breach test.",
    }
    response = client.post("/api/simulation/trigger", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["drone_id"] == "Drone-Test"
    assert data["threat_level"] == "HIGH"
    assert data["category"] == "PERIMETER_BREACH"


def test_get_incidents_endpoint(client: TestClient) -> None:
    """Test GET /api/incidents returns incidents list."""
    response = client.get("/api/incidents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
