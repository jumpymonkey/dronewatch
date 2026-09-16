"""Drone video stream processor for RTSP live feeds and GCS MP4 files."""

import asyncio
import logging
import os
import time
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


def format_video_timestamp(seconds: float | None) -> str | None:
    """Format timestamp seconds into MM:SS or HH:MM:SS string format."""
    if seconds is None or seconds < 0:
        return None
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def get_gcs_cache_path(stream_url: str) -> str | None:
    """Return local cache path for a GCS URL if file exists and is non-empty."""
    if not stream_url.startswith("gs://"):
        return None
    gcs_path = stream_url[5:]
    parts = gcs_path.split("/", 1)
    bucket_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""
    cached_file = os.path.join("/tmp/gcs_cache", f"{bucket_name}_{os.path.basename(blob_name)}")
    if os.path.exists(cached_file) and os.path.getsize(cached_file) > 0:
        return cached_file
    return None


def cleanup_gcs_cache(keep_file: str | None = None) -> None:
    """Clean up older cached video files in /tmp/gcs_cache to free RAM in Cloud Run."""
    cache_dir = "/tmp/gcs_cache"
    if not os.path.exists(cache_dir):
        return
    try:
        for fname in os.listdir(cache_dir):
            fpath = os.path.join(cache_dir, fname)
            if os.path.isfile(fpath) and fpath != keep_file:
                try:
                    os.remove(fpath)
                    logger.info("Purged older cached video file to free memory: %s", fpath)
                except Exception as ex:
                    logger.warning("Could not remove cache file %s: %s", fpath, ex)
    except Exception as ex:
        logger.warning("Cache cleanup error: %s", ex)


def ensure_gcs_cached(stream_url: str, gcp_project_id: str = "") -> str | None:
    """Download GCS blob gs://bucket/path to local cache if missing or 0 bytes."""
    if not stream_url.startswith("gs://"):
        return None

    gcs_path = stream_url[5:]
    parts = gcs_path.split("/", 1)
    bucket_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""

    cache_dir = "/tmp/gcs_cache"
    os.makedirs(cache_dir, exist_ok=True)
    cached_file = os.path.join(cache_dir, f"{bucket_name}_{os.path.basename(blob_name)}")
    temp_file = f"{cached_file}.tmp"

    if not os.path.exists(cached_file) or os.path.getsize(cached_file) == 0:
        # Purge older cached files to keep /tmp memory usage minimal
        cleanup_gcs_cache(keep_file=cached_file)

        if os.path.exists(temp_file):
            for _ in range(30):
                if os.path.exists(cached_file) and os.path.getsize(cached_file) > 0:
                    return cached_file
                time.sleep(0.5)

        try:
            logger.info("Downloading GCS blob gs://%s/%s to cache...", bucket_name, blob_name)
            from google.cloud import storage

            storage_client = storage.Client(project=gcp_project_id or None)
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.download_to_filename(temp_file)
            os.replace(temp_file, cached_file)
            logger.info("Downloaded GCS blob to %s", cached_file)
        except Exception as ex:
            logger.error("Failed to download GCS video %s: %s", stream_url, ex)
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            if os.path.exists(cached_file) and os.path.getsize(cached_file) == 0:
                try:
                    os.remove(cached_file)
                except Exception:
                    pass
            return None

    return cached_file


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
        if self.config.stream_url and self.config.stream_url.lower().startswith("rtsp://"):
            self.config.stream_url = "rtsp://" + self.config.stream_url.strip()[7:]
        self.settings: Settings = settings
        self.analyzer: GeminiVideoAnalyzer = analyzer
        self.event_callback: EventCallback | None = event_callback
        self.motion_filter: MotionFilter = MotionFilter(
            sensitivity_threshold=settings.motion_sensitivity_threshold,
            min_motion_area=settings.min_motion_area,
        )
        self.is_running: bool = False
        self._task: asyncio.Task[None] | None = None
        self.latest_frame_bytes: bytes | None = None

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

        async def _analyze_frame_task(
            frame_bytes_data: bytes, video_timestamp_sec: float | None = None
        ) -> None:
            try:
                analysis = await self.analyzer.analyze_frame(
                    frame_bytes_data, mime_type="image/jpeg"
                )
                threat_active = (
                    analysis.suspicious_activity_detected
                    or analysis.threat_level != ThreatLevel.NONE
                )

                formatted_timecode = format_video_timestamp(video_timestamp_sec)

                if threat_active:
                    self.config.status = StreamStatus.ALERT
                    logger.warning(
                        "DISPATCH ALERT from Drone %s [TC %s]: [%s] %s",
                        self.config.drone_id,
                        formatted_timecode or "N/A",
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
                    video_timestamp_seconds=video_timestamp_sec,
                    video_timestamp_formatted=formatted_timecode,
                )

                if self.event_callback:
                    await self.event_callback(event)
            except Exception as ex:
                logger.error("Error in background frame analysis task: %s", ex)

        # Resolve GCS gs:// path to local cached file if needed
        local_video_path = self.config.stream_url
        if self.config.stream_url.startswith("gs://"):
            cached_path = await asyncio.to_thread(
                ensure_gcs_cached, self.config.stream_url, self.settings.gcp_project_id
            )
            if cached_path:
                local_video_path = cached_path

        # PyAV demuxer path for local files with multi-stream / attached-picture MP4s
        if os.path.exists(local_video_path) and os.path.isfile(local_video_path):
            logger.info("Using PyAV demuxer for video file: %s", local_video_path)
            try:
                container = av.open(local_video_path)
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
                            frame_time = float(frame.time)
                            target_time = frame.time + sample_interval

                            # Run motion filter
                            has_motion, motion_score = self.motion_filter.process_frame(img_bgr)

                            success, buffer = cv2.imencode(".jpg", img_bgr)
                            if success:
                                frame_data = buffer.tobytes()
                                self.latest_frame_bytes = frame_data

                                if has_motion:
                                    active_analysis_tasks = {
                                        t for t in active_analysis_tasks if not t.done()
                                    }
                                    if len(active_analysis_tasks) < max_concurrent_analysis:
                                        task = asyncio.create_task(
                                            _analyze_frame_task(frame_data, frame_time)
                                        )
                                        active_analysis_tasks.add(task)
                                else:
                                    logger.debug(
                                        "Motion filter skipped static frame for drone %s at TC %s",
                                        self.config.drone_id,
                                        frame_time,
                                    )

                            await asyncio.sleep(sample_interval)

                    if self.is_running:
                        try:
                            container.seek(0)
                            target_time = 0.0
                        except Exception:
                            container.close()
                            container = av.open(local_video_path)
                            target_time = 0.0

                container.close()
                return
            except asyncio.CancelledError:
                return
            except Exception as pyav_err:
                logger.warning("PyAV demuxer error: %s. Falling back to OpenCV.", pyav_err)

        # OpenCV fallback path for RTSP / HTTP live feeds
        def _open_cap():
            cap = cv2.VideoCapture(self.config.stream_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cap

        cap = await asyncio.to_thread(_open_cap)
        if not cap.isOpened():
            logger.error("Failed to open stream target: %s", self.config.stream_url)
            self.config.status = StreamStatus.OFFLINE
            return

        def _get_frame():
            if not self.is_running:
                return False, None, None
            ret, frame = cap.read()
            if (not ret or frame is None) and self.is_running:
                cap.open(self.config.stream_url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ret, frame = cap.read()
            pos_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
            pos_sec = pos_msec / 1000.0 if pos_msec > 0 else None
            return ret, frame, pos_sec

        last_ai_time = 0.0
        try:
            while self.is_running:
                ret, frame, pos_sec = await asyncio.to_thread(_get_frame)
                if not ret or frame is None or not self.is_running:
                    await asyncio.sleep(0.1)
                    continue

                success, buffer = cv2.imencode(".jpg", frame)
                if success:
                    frame_data = buffer.tobytes()
                    self.latest_frame_bytes = frame_data

                    now = time.time()
                    if now - last_ai_time >= sample_interval:
                        last_ai_time = now
                        has_motion, motion_score = self.motion_filter.process_frame(frame)
                        if has_motion:
                            active_analysis_tasks = {
                                t for t in active_analysis_tasks if not t.done()
                            }
                            if len(active_analysis_tasks) < max_concurrent_analysis:
                                task = asyncio.create_task(_analyze_frame_task(frame_data, pos_sec))
                                active_analysis_tasks.add(task)
                        else:
                            logger.debug(
                                "Motion filter skipped static frame for drone %s",
                                self.config.drone_id,
                            )

                await asyncio.sleep(0.01)

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
