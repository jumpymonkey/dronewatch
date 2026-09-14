"""Drone video stream processor for RTSP live feeds and GCS MP4 files."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

import cv2

from dronewatch.config import Settings
from dronewatch.models.events import (
    DroneStreamConfig,
    IncidentEvent,
    Location,
    StreamStatus,
    ThreatLevel,
)
from dronewatch.services.analyzer import GeminiVideoAnalyzer
from dronewatch.services.motion_filter import MotionFilter

logger = logging.getLogger(__name__)

EventCallback = Callable[[IncidentEvent], Coroutine[Any, Any, None]]


class DroneStreamProcessor:
    """Ingests and processes drone video streams (RTSP or MP4 file)."""

    def __init__(
        self,
        config: DroneStreamConfig,
        settings: Settings,
        analyzer: GeminiVideoAnalyzer,
        event_callback: EventCallback | None = None,
    ) -> None:
        """Initialize stream processor.

        Args:
            config: Drone stream configuration model.
            settings: Global settings instance.
            analyzer: Gemini analyzer instance.
            event_callback: Async callback invoked when an incident event is logged.
        """
        self.config: DroneStreamConfig = config
        self.settings: Settings = settings
        self.analyzer: GeminiVideoAnalyzer = analyzer
        self.event_callback: EventCallback | None = event_callback
        self.motion_filter: MotionFilter = MotionFilter(
            sensitivity_threshold=settings.motion_sensitivity_threshold,
            min_motion_area=settings.min_motion_area,
        )
        self.is_running: bool = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the stream processing background task."""
        if self.is_running:
            return
        self.is_running = True
        self.config.status = StreamStatus.ONLINE
        self._task = asyncio.create_task(self._process_loop())
        logger.info(
            "Started stream processor for drone %s (%s)",
            self.config.drone_id,
            self.config.stream_url,
        )

    async def stop(self) -> None:
        """Stop stream processor gracefully."""
        self.is_running = False
        self.config.status = StreamStatus.OFFLINE
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=0.5)
            except (TimeoutError, asyncio.CancelledError):
                pass
        logger.info("Stopped stream processor for drone %s", self.config.drone_id)

    async def _process_loop(self) -> None:
        """Main frame extraction and analysis loop."""

        def _open_cap():
            return cv2.VideoCapture(self.config.stream_url)

        cap = await asyncio.to_thread(_open_cap)
        if not cap.isOpened():
            logger.error("Failed to open stream target: %s", self.config.stream_url)
            self.config.status = StreamStatus.OFFLINE
            return

        def _get_frame():
            if not self.is_running:
                return False, None
            ret, frame = cap.read()
            if (not ret or frame is None) and self.is_running:
                # Re-open stream target to seamlessly loop video files or recover RTSP feeds
                cap.open(self.config.stream_url)
                ret, frame = cap.read()
            return ret, frame

        active_analysis_tasks: set[asyncio.Task[None]] = set()
        max_concurrent_analysis: int = 3

        async def _analyze_frame_task(frame_bytes_data: bytes) -> None:
            try:
                analysis = await self.analyzer.analyze_frame(
                    frame_bytes_data, mime_type="image/jpeg"
                )
                threat_active = (
                    analysis.suspicious_activity_detected
                    or analysis.threat_level != ThreatLevel.NONE
                )

                if threat_active:
                    self.config.status = StreamStatus.ALERT
                    logger.warning(
                        "DISPATCH ALERT from Drone %s: [%s] %s",
                        self.config.drone_id,
                        analysis.threat_level,
                        analysis.summary,
                    )
                else:
                    self.config.status = StreamStatus.ONLINE

                event = IncidentEvent(
                    drone_id=self.config.drone_id,
                    timestamp=datetime.utcnow(),
                    location=Location(zone_name=self.config.zone_name),
                    threat_level=analysis.threat_level,
                    category=analysis.category,
                    description=analysis.summary or analysis.description,
                    confidence_score=analysis.confidence_score,
                    bounding_boxes=analysis.bounding_boxes,
                    snapshot_uri=None,
                )

                if self.event_callback:
                    await self.event_callback(event)
            except Exception as ex:
                logger.error("Error in background frame analysis task: %s", ex)

        try:
            while self.is_running:
                ret, frame = await asyncio.to_thread(_get_frame)
                if not ret or frame is None or not self.is_running:
                    await asyncio.sleep(0.5)
                    continue

                # Run motion filter
                has_motion, _ = self.motion_filter.process_frame(frame)

                # Clean up finished tasks from previous iterations
                active_analysis_tasks = {t for t in active_analysis_tasks if not t.done()}

                if len(active_analysis_tasks) < max_concurrent_analysis:
                    success, buffer = cv2.imencode(".jpg", frame)
                    if success:
                        frame_bytes: bytes = buffer.tobytes()
                        task = asyncio.create_task(_analyze_frame_task(frame_bytes))
                        active_analysis_tasks.add(task)

                # Throttle frame extraction rate according to configured sampling FPS
                await asyncio.sleep(1.0 / self.settings.frame_sampling_fps)

        except asyncio.CancelledError:
            pass
        except Exception as err:
            logger.error(
                "Error in stream processor loop for %s: %s",
                self.config.drone_id,
                err,
                exc_info=True,
            )
        finally:
            cap.release()
            self.config.status = StreamStatus.OFFLINE
