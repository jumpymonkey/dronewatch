"""FastAPI application entry point for DroneWatch backend service."""

import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
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
from dronewatch.services.stream_processor import (
    DroneStreamProcessor,
    get_gcs_cache_path,
)

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
    if req.drone_id in stream_processors:
        old_processor = stream_processors.pop(req.drone_id)
        await old_processor.stop()

    if len(active_streams) >= settings.max_concurrent_streams:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum concurrent streams limit ({settings.max_concurrent_streams}) reached.",
        )

    clean_url = req.stream_url.strip()
    if clean_url.lower().startswith("rtsp://"):
        clean_url = "rtsp://" + clean_url[7:]

    config = DroneStreamConfig(
        drone_id=req.drone_id,
        stream_url=clean_url,
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


def send_range_file_response(
    file_path: str, request: Request, media_type: str = "video/mp4"
) -> Response:
    """Stream local video file supporting HTTP 206 Partial Content range requests."""
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")

    if not range_header:
        return FileResponse(path=file_path, media_type=media_type)

    try:
        range_str = range_header.strip().lower().replace("bytes=", "")
        r_parts = range_str.split("-")
        start = int(r_parts[0]) if r_parts[0] else 0
        chunk_size = 10 * 1024 * 1024  # 10MB range chunk
        default_end = min(start + chunk_size - 1, file_size - 1)

        end = int(r_parts[1]) if len(r_parts) > 1 and r_parts[1] else default_end
        end = min(end, file_size - 1)

        if start >= file_size or start > end:
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{file_size}"},
            )

        length = end - start + 1
        with open(file_path, "rb") as f:
            f.seek(start)
            data = f.read(length)

        return Response(
            content=data,
            status_code=206,
            media_type=media_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
            },
        )
    except Exception as ex:
        logger.error("Failed local file range stream for %s: %s", file_path, ex)
        return FileResponse(path=file_path, media_type=media_type)


def stream_gcs_range_response(gs_url: str, request: Request, project_id: str) -> Response:
    """Stream byte ranges directly from GCS blob for instant browser video playback."""
    try:
        from google.cloud import storage

        clean_path = gs_url.replace("gs://", "")
        parts = clean_path.split("/", 1)
        bucket_name = parts[0]
        blob_name = parts[1] if len(parts) > 1 else ""

        client = storage.Client(project=project_id)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.reload()
        total_size = blob.size
        content_type = blob.content_type or "video/mp4"

        range_header = request.headers.get("range")
        if range_header:
            range_str = range_header.strip().lower().replace("bytes=", "")
            r_parts = range_str.split("-")
            start = int(r_parts[0]) if r_parts[0] else 0
            chunk_size = 10 * 1024 * 1024  # 10MB range chunk
            default_end = min(start + chunk_size - 1, total_size - 1)
            end = int(r_parts[1]) if len(r_parts) > 1 and r_parts[1] else default_end
            end = min(end, total_size - 1)
        else:
            start = 0
            end = min(10 * 1024 * 1024 - 1, total_size - 1)

        length = end - start + 1
        data = blob.download_as_bytes(start=start, end=end)
        return Response(
            content=data,
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{total_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
            },
        )
    except Exception as ex:
        logger.error("Failed GCS range stream for %s: %s", gs_url, ex)
        return RedirectResponse(url=FALLBACK_VIDEO_URL)


@app.get("/api/streams/{drone_id}/video")
async def get_stream_video(drone_id: str, request: Request, stream_url: str | None = None) -> Any:
    """Serve video content for a registered drone stream feed or GCS video source."""
    config = active_streams.get(drone_id)
    target_url = config.stream_url if config else stream_url

    if not target_url:
        possible_gcs = f"gs://{settings.gcs_bucket_videos}/{drone_id}"
        if not drone_id.lower().endswith(".mp4"):
            possible_gcs += ".MP4"
        target_url = possible_gcs

    # Serve local video file if path exists on disk and is non-empty
    if (
        os.path.exists(target_url)
        and os.path.isfile(target_url)
        and os.path.getsize(target_url) > 0
    ):
        return send_range_file_response(target_url, request)

    if target_url.startswith("gs://"):
        cached_file = get_gcs_cache_path(target_url)
        if cached_file:
            return send_range_file_response(cached_file, request)

        return await asyncio.to_thread(
            stream_gcs_range_response, target_url, request, settings.gcp_project_id
        )

    # Serve live MJPEG stream for RTSP feeds
    if target_url and target_url.lower().startswith("rtsp://"):

        async def mjpeg_generator() -> AsyncGenerator[bytes, None]:
            start_time = time.time()
            while True:
                proc = stream_processors.get(drone_id)
                if proc and proc.is_running:
                    if proc.latest_frame_bytes:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + proc.latest_frame_bytes + b"\r\n"
                        )
                    else:
                        # Wait for RTSP stream to initialize
                        if time.time() - start_time > 30.0:
                            logger.warning(
                                "RTSP stream %s timed out waiting for initial frame", drone_id
                            )
                            break
                        await asyncio.sleep(0.1)
                        continue
                else:
                    # Give processor time to start if stream was just registered
                    if time.time() - start_time > 10.0:
                        break
                    await asyncio.sleep(0.1)
                    continue

                await asyncio.sleep(0.033)

        return StreamingResponse(
            mjpeg_generator(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    # Redirect to HTTP(S) URL if provided directly
    if target_url.startswith("http://") or target_url.startswith("https://"):
        return RedirectResponse(url=target_url)

    # Fallback for unresolved streams
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


# Static files mounting for single-container deployment on Cloud Run
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/dist"))

if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
