"""FastAPI application entry point for DroneWatch backend service."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from dronewatch.config import get_settings
from dronewatch.db.alloydb import AlloyDBManager
from dronewatch.models.events import (
    DroneStreamConfig,
    IncidentCategory,
    IncidentEvent,
    Location,
    StreamStatus,
    ThreatLevel,
)
from dronewatch.services.analyzer import GeminiVideoAnalyzer
from dronewatch.services.stream_processor import DroneStreamProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dronewatch")

settings = get_settings()
db_manager = AlloyDBManager(settings)
analyzer = GeminiVideoAnalyzer(settings)

# Global active streams and processors registry
active_streams: dict[str, DroneStreamConfig] = {}
stream_processors: dict[str, DroneStreamProcessor] = {}
connected_websockets: list[WebSocket] = []

FALLBACK_VIDEO_URL = (
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
)


class StreamRegisterRequest(BaseModel):
    """Payload to register a drone video stream."""

    model_config = ConfigDict(extra="forbid")

    drone_id: str = Field(..., description="Unique drone identifier e.g., Drone-Alpha")
    stream_url: str = Field(..., description="RTSP URL or local/gs:// MP4 file path")
    zone_name: str = Field(..., description="Assigned campus zone name")


class SimulationTriggerRequest(BaseModel):
    """Payload to trigger a simulated security event."""

    model_config = ConfigDict(extra="forbid")

    drone_id: str = Field(default="Drone-01")
    threat_level: ThreatLevel = Field(default=ThreatLevel.HIGH)
    category: IncidentCategory = Field(default=IncidentCategory.PERIMETER_BREACH)
    description: str = Field(
        default="Unauthorized individual spotted climbing perimeter fence near Gate 4 after hours."
    )


async def broadcast_incident(event: IncidentEvent) -> None:
    """Broadcast an incident event to AlloyDB and all connected WebSocket clients."""
    await db_manager.log_incident(event)

    payload = event.model_dump_json()
    disconnected: list[WebSocket] = []

    for ws in connected_websockets:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        if ws in connected_websockets:
            connected_websockets.remove(ws)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager initializing DB pool."""
    logger.info("Initializing DroneWatch application lifespan...")
    await db_manager.connect()

    yield

    logger.info("Shutting down DroneWatch application lifespan...")
    for processor in list(stream_processors.values()):
        await processor.stop()
    await db_manager.close()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Multi-Drone Video Analysis & Alerting System using Gemini 3.6 Flash and AlloyDB",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
        "gemini_model": settings.gemini_model,
        "active_streams_count": len(active_streams),
    }


@app.get("/api/streams")
async def list_streams() -> list[DroneStreamConfig]:
    """List all registered active drone video streams."""
    return list(active_streams.values())


@app.post("/api/streams")
async def register_stream(req: StreamRegisterRequest) -> DroneStreamConfig:
    """Register and launch a new drone video stream feed."""
    if len(active_streams) >= settings.max_concurrent_streams:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum concurrent streams limit ({settings.max_concurrent_streams}) reached.",
        )

    config = DroneStreamConfig(
        drone_id=req.drone_id,
        stream_url=req.stream_url,
        zone_name=req.zone_name,
        status=StreamStatus.ONLINE,
    )
    active_streams[req.drone_id] = config

    processor = DroneStreamProcessor(
        config=config,
        settings=settings,
        analyzer=analyzer,
        event_callback=broadcast_incident,
    )
    stream_processors[req.drone_id] = processor
    await processor.start()

    return config


@app.delete("/api/streams/{drone_id}")
async def unregister_stream(drone_id: str) -> dict[str, Any]:
    """Unregister and stop an active drone video stream feed."""
    if drone_id not in active_streams:
        raise HTTPException(status_code=404, detail=f"Stream '{drone_id}' not found.")

    if drone_id in stream_processors:
        processor = stream_processors.pop(drone_id)
        await processor.stop()

    active_streams.pop(drone_id, None)
    logger.info("Unregistered stream for drone %s", drone_id)
    return {
        "status": "success",
        "drone_id": drone_id,
        "message": "Stream unregistered successfully.",
    }


@app.get("/api/streams/{drone_id}/video")
async def get_stream_video(drone_id: str) -> Any:
    """Serve video content for a registered drone stream feed."""
    if drone_id not in active_streams:
        return RedirectResponse(url=FALLBACK_VIDEO_URL)

    config = active_streams[drone_id]
    stream_url = config.stream_url

    # Serve local video file if path exists on disk
    if os.path.exists(stream_url) and os.path.isfile(stream_url):
        return FileResponse(path=stream_url, media_type="video/mp4")

    # Redirect to HTTP(S) URL if provided directly
    if stream_url.startswith("http://") or stream_url.startswith("https://"):
        return RedirectResponse(url=stream_url)

    # Fallback for RTSP/GCS streams
    return RedirectResponse(url=FALLBACK_VIDEO_URL)


@app.get("/api/incidents")
async def get_incidents(limit: int = 50, threat: ThreatLevel | None = None) -> list[IncidentEvent]:
    """Retrieve logged security incident events from AlloyDB."""
    return await db_manager.get_recent_incidents(limit=limit, threat_filter=threat)


@app.post("/api/incidents/{event_id}/acknowledge")
async def acknowledge_incident(event_id: UUID) -> dict[str, Any]:
    """Acknowledge an incident alert."""
    success = await db_manager.acknowledge_incident(event_id)
    if not success:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return {"status": "success", "event_id": str(event_id), "acknowledged": True}


@app.post("/api/simulation/trigger")
async def trigger_simulated_alert(req: SimulationTriggerRequest) -> IncidentEvent:
    """Trigger a simulated security alert for pilot dashboard testing."""
    event = IncidentEvent(
        drone_id=req.drone_id,
        threat_level=req.threat_level,
        category=req.category,
        description=req.description,
        confidence_score=0.92,
        location=Location(zone_name="Simulated Patrol Zone"),
    )
    await broadcast_incident(event)
    return event


@app.websocket("/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time pilot dashboard alert broadcasts."""
    await websocket.accept()
    connected_websockets.append(websocket)
    logger.info("WebSocket pilot client connected. Total clients: %d", len(connected_websockets))

    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info("WebSocket pilot client disconnected.")
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)
