"""Drone video stream processor for RTSP live feeds and GCS MP4 files."""

import asyncio
import logging
import os
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

import av
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
        active_analysis_tasks: set[asyncio.Task[None]] = set()
        max_concurrent_analysis: int = 3
        sample_interval: float = 1.0 / self.settings.frame_sampling_fps

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

        # PyAV demuxer path for local files with multi-stream / attached-picture MP4s
        if os.path.exists(self.config.stream_url) and os.path.isfile(self.config.stream_url):
            logger.info("Using PyAV demuxer for video file: %s", self.config.stream_url)
            try:
                container = av.open(self.config.stream_url)
                video_streams = [
                    s
                    for s in container.streams.video
                    if s.codec_context and s.codec_context.name != "mjpeg"
                ]
                video_stream = max(
                    video_streams or container.streams.video,
                    key=lambda s: s.width * s.height,
                )

                target_time = 0.0

                while self.is_running:
                    for frame in container.decode(video_stream):
                        if not self.is_running:
                            break

                        if frame.time is not None and frame.time >= target_time:
                            img_bgr = frame.to_ndarray(format="bgr24")
                            target_time = frame.time + sample_interval

                            # Run motion filter
                            self.motion_filter.process_frame(img_bgr)

                            active_analysis_tasks = {
                                t for t in active_analysis_tasks if not t.done()
                            }
                            if len(active_analysis_tasks) < max_concurrent_analysis:
                                success, buffer = cv2.imencode(".jpg", img_bgr)
                                if success:
                                    frame_data = buffer.tobytes()
                                    task = asyncio.create_task(_analyze_frame_task(frame_data))
                                    active_analysis_tasks.add(task)

                            await asyncio.sleep(sample_interval)

                    if self.is_running:
                        try:
                            container.seek(0)
                            target_time = 0.0
                        except Exception:
                            container.close()
                            container = av.open(self.config.stream_url)
                            target_time = 0.0

                container.close()
                return
            except asyncio.CancelledError:
                return
            except Exception as pyav_err:
                logger.warning("PyAV demuxer error: %s. Falling back to OpenCV.", pyav_err)

        # OpenCV fallback path for RTSP / HTTP live feeds
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
                cap.open(self.config.stream_url)
                ret, frame = cap.read()
            return ret, frame

        try:
            while self.is_running:
                ret, frame = await asyncio.to_thread(_get_frame)
                if not ret or frame is None or not self.is_running:
                    await asyncio.sleep(0.5)
                    continue

                self.motion_filter.process_frame(frame)
                active_analysis_tasks = {t for t in active_analysis_tasks if not t.done()}

                if len(active_analysis_tasks) < max_concurrent_analysis:
                    success, buffer = cv2.imencode(".jpg", frame)
                    if success:
                        task = asyncio.create_task(_analyze_frame_task(buffer.tobytes()))
                        active_analysis_tasks.add(task)

                await asyncio.sleep(sample_interval)

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
