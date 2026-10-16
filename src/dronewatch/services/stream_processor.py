"""Drone video stream processor for RTSP live feeds and GCS MP4 files."""

import asyncio
import logging
import os
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

import av
import cv2

from dronewatch.config import Settings
from dronewatch.models.events import (
    DroneStreamConfig,
    IncidentCategory,
    IncidentEvent,
    Location,
    StreamStatus,
    ThreatLevel,
)
from dronewatch.models.workflow_config import EscalationTarget, WorkflowConfig
from dronewatch.services.analyzer import GeminiVideoAnalyzer
from dronewatch.services.gemma_client import GemmaTriageClient
from dronewatch.services.motion_filter import MotionFilter

logger = logging.getLogger(__name__)

EventCallback = Callable[[IncidentEvent], Coroutine[Any, Any, None]]
ConfigProvider = Callable[[], Coroutine[Any, Any, WorkflowConfig] | WorkflowConfig]


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


def normalize_stream_url(stream_url: str, default_bucket: str = "") -> str:
    """Normalize stream URL, resolving placeholders, bare filenames, and GCS paths."""
    url = stream_url.strip()
    if not url:
        return url

    # RTSP streams
    if url.lower().startswith("rtsp://"):
        return "rtsp://" + url[7:].strip()

    # Direct HTTP/HTTPS streams
    if url.lower().startswith(("http://", "https://")):
        return url

    # Local file path if existing on the current filesystem
    if os.path.exists(url) and os.path.isfile(url):
        return url

    target_bucket = default_bucket or "jal-dronewatch-videos"

    placeholder_buckets = {
        "dronewatch-videos-bucket",
        "dronewatch-dronevideos-bucket",
        "dronewatch-sample-videos",
        "dronewatch-bucket",
    }

    if url.startswith("gs://"):
        gcs_path = url[5:].strip()
        parts = gcs_path.split("/", 1)
        bucket = parts[0]
        blob = parts[1] if len(parts) > 1 else ""

        # E.g. gs://S1001976.MP4 where user omitted the bucket
        if not blob and bucket.lower().endswith((".mp4", ".mov", ".mkv", ".avi")):
            return f"gs://{target_bucket}/{bucket}"

        # Remap placeholder bucket to actual bucket
        if bucket.lower() in placeholder_buckets or not bucket:
            return f"gs://{target_bucket}/{blob}"

        return f"gs://{bucket}/{blob}"

    # If it's a bare filename or relative path
    basename = os.path.basename(url)
    if basename.lower().endswith((".mp4", ".mov", ".mkv", ".avi")):
        return f"gs://{target_bucket}/{basename}"

    # If no extension is specified, default to .MP4 in GCS
    if "." not in basename:
        return f"gs://{target_bucket}/{basename}.MP4"

    return url


def get_gcs_cache_path(stream_url: str, default_bucket: str = "") -> str | None:
    """Return local cache path for a GCS URL if file exists and is non-empty."""
    normalized = normalize_stream_url(stream_url, default_bucket=default_bucket)
    if not normalized.startswith("gs://"):
        return None
    gcs_path = normalized[5:]
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


def ensure_gcs_cached(
    stream_url: str, gcp_project_id: str = "", default_bucket: str = ""
) -> str | None:
    """Download GCS blob gs://bucket/path to local cache if missing or 0 bytes."""
    normalized = normalize_stream_url(stream_url, default_bucket=default_bucket)
    if not normalized.startswith("gs://"):
        return None

    gcs_path = normalized[5:]
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
            os.environ["CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE"] = "false"
            os.environ["GOOGLE_API_CERTIFICATE_CONFIG"] = ""
            from google.cloud import storage

            storage_client = storage.Client(project=gcp_project_id or None)
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.download_to_filename(temp_file)
            os.replace(temp_file, cached_file)
            logger.info("Downloaded GCS blob to %s", cached_file)
        except Exception as ex:
            logger.error("Failed to download GCS video %s: %s", normalized, ex)
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
        gemma_client: GemmaTriageClient | None = None,
        event_callback: EventCallback | None = None,
        config_provider: ConfigProvider | None = None,
    ) -> None:
        """Initialize stream processor.

        Args:
            config: Drone stream configuration model.
            settings: Global settings instance.
            analyzer: Gemini analyzer instance.
            gemma_client: Optional Tier 1 Gemma 4 triage client.
            event_callback: Async callback invoked when an incident event is logged.
            config_provider: Optional callable returning dynamic WorkflowConfig.
        """
        self.config: DroneStreamConfig = config
        if self.config.stream_url:
            self.config.stream_url = normalize_stream_url(
                self.config.stream_url, default_bucket=settings.gcs_bucket_videos
            )
        self.settings: Settings = settings
        self.analyzer: GeminiVideoAnalyzer = analyzer
        self.event_callback: EventCallback | None = event_callback
        self.config_provider: ConfigProvider | None = config_provider
        self.motion_filter: MotionFilter = MotionFilter(
            sensitivity_threshold=settings.motion_sensitivity_threshold,
            min_motion_area=settings.min_motion_area,
        )
        if gemma_client is not None:
            self.gemma_client: GemmaTriageClient | None = gemma_client
            self._owns_gemma_client: bool = False
        else:
            self.gemma_client = GemmaTriageClient(settings)
            self._owns_gemma_client = True

        self.is_running: bool = False
        self._task: asyncio.Task[None] | None = None
        self.latest_frame_bytes: bytes | None = None
        # Track periodic Gemma scene description updates (every ~10s)
        self._last_scene_description_time: float = -100.0
        self._last_scene_description_wall: float = 0.0

    async def _get_active_workflow_config(self) -> WorkflowConfig:
        """Retrieve dynamic active workflow configuration or static fallback."""
        if self.config_provider is not None:
            try:
                res = self.config_provider()
                if asyncio.iscoroutine(res):
                    return await res
                return res  # type: ignore[return-value]
            except Exception as err:
                logger.error("Error retrieving dynamic workflow config: %s", err)

        return WorkflowConfig(
            enable_tier1_gemma=self.settings.enable_tier1_gemma,
            gemma_triage_prompt=self.settings.gemma_triage_prompt,
            gemma_triage_threshold=self.settings.gemma_triage_threshold,
            escalation_target=EscalationTarget.GEMINI,
            gemini_model=self.settings.gemini_model,
            gemma_model=self.settings.gemma_model_name,
            gemma_service_url=self.settings.gemma_service_url,
            gemma_timeout_seconds=self.settings.gemma_timeout_seconds,
        )

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
        if self._owns_gemma_client and self.gemma_client is not None:
            await self.gemma_client.aclose()
        logger.info("Stopped stream processor for drone %s", self.config.drone_id)

    async def _analyze_frame(
        self,
        frame_bytes_data: bytes,
        video_timestamp_sec: float | None = None,
        is_heartbeat: bool = False,
    ) -> None:
        """Execute two-tier analysis on a single frame based on dynamic WorkflowConfig.

        Tier 1 (Gemma 4): Fast front-line vision triage & routine scene heartbeat.
        Tier 2 (Gemini Flash or Gemma 4): Escalated multimodal threat assessment.
        """
        try:
            formatted_timecode = format_video_timestamp(video_timestamp_sec)
            workflow_config = await self._get_active_workflow_config()

            # Tier 1: Front-line vision triage via Gemma 4 (Cloud Run GPU)
            if self.gemma_client and workflow_config.enable_tier1_gemma:
                triage = await self.gemma_client.triage_frame(
                    frame_bytes=frame_bytes_data,
                    drone_id=self.config.drone_id,
                    timestamp_sec=video_timestamp_sec,
                    request_scene_description=is_heartbeat,
                    prompt=workflow_config.gemma_triage_prompt,
                    threshold=workflow_config.gemma_triage_threshold,
                    gemma_service_url=workflow_config.gemma_service_url,
                    gemma_model=workflow_config.gemma_model,
                    gemma_timeout_seconds=workflow_config.gemma_timeout_seconds,
                    alert_keywords=workflow_config.alert_keywords,
                    benign_keywords=workflow_config.benign_keywords,
                    ambiguity_policy=workflow_config.ambiguity_policy,
                    vllm_temperature=workflow_config.vllm_temperature,
                    vllm_max_tokens=workflow_config.vllm_max_tokens,
                )
                if not triage.escalate_to_gemini:
                    if is_heartbeat:
                        scene_desc = (
                            triage.scene_description
                            or triage.raw_output
                            or "Routine aerial surveillance - zone clear."
                        )
                        logger.info(
                            "Tier 1 Gemma scene heartbeat for %s [TC %s]: %s (latency=%.1fms)",
                            self.config.drone_id,
                            formatted_timecode or "N/A",
                            scene_desc,
                            triage.tier1_latency_ms,
                        )
                        event = IncidentEvent(
                            drone_id=self.config.drone_id,
                            timestamp=datetime.now(UTC),
                            location=Location(zone_name=self.config.zone_name),
                            threat_level=ThreatLevel.NONE,
                            category=IncidentCategory.CLEAR,
                            description=f"Gemma 4 Triage: {scene_desc}",
                            confidence_score=round(1.0 - triage.triage_score, 2),
                            bounding_boxes=[],
                            snapshot_uri=None,
                            video_timestamp_seconds=video_timestamp_sec,
                            video_timestamp_formatted=formatted_timecode,
                            source_tier="triage",
                            source_model="gemma",
                            model_name=triage.model_name or self.settings.gemma_model_name,
                            scene_summary=scene_desc,
                            raw_response=triage.raw_output,
                            latency_ms=triage.tier1_latency_ms,
                        )
                        if self.event_callback:
                            await self.event_callback(event)
                        return

                    logger.info(
                        "Tier 1 Gemma suppressed benign frame for %s [TC %s]: %s "
                        "(score=%.2f, latency=%.1fms, tags=%s)",
                        self.config.drone_id,
                        formatted_timecode or "N/A",
                        triage.raw_output.strip() if triage.raw_output else "SAFE",
                        triage.triage_score,
                        triage.tier1_latency_ms,
                        triage.tags,
                    )
                    return

                logger.info(
                    "Tier 1 Gemma escalated frame for %s [TC %s]: response='%s' "
                    "(decision=%s, score=%.2f, latency=%.1fms, tags=%s)",
                    self.config.drone_id,
                    formatted_timecode or "N/A",
                    triage.raw_output.strip() if triage.raw_output else "",
                    triage.tier1_decision,
                    triage.triage_score,
                    triage.tier1_latency_ms,
                    triage.tags,
                )

            # Tier 2: Deep Contextual Reasoning via Gemini 3.6 Flash or Gemma 4
            target_is_gemma = (
                workflow_config.escalation_target == EscalationTarget.GEMMA
                and self.gemma_client is not None
            )
            if target_is_gemma:
                source_tier = "escalation"
                source_model = "gemma"
                model_name = (
                    workflow_config.gemma_model
                    or getattr(self.gemma_client, "model_name", None)
                    or self.settings.gemma_model_name
                )
                analysis = await self.gemma_client.deep_analyze_frame(
                    frame_bytes=frame_bytes_data,
                    escalation_prompt=workflow_config.gemma_escalation_prompt,
                    drone_id=self.config.drone_id,
                    gemma_service_url=workflow_config.gemma_service_url,
                    gemma_model=workflow_config.gemma_model,
                    gemma_timeout_seconds=workflow_config.gemma_timeout_seconds,
                    vllm_temperature=workflow_config.vllm_temperature,
                    vllm_max_tokens=workflow_config.vllm_max_tokens,
                )
            else:
                source_tier = "escalation"
                source_model = "gemini"
                model_name = (
                    workflow_config.gemini_model
                    or getattr(self.analyzer, "model", None)
                    or self.settings.gemini_model
                )
                analysis = await self.analyzer.analyze_frame(
                    image_bytes=frame_bytes_data,
                    mime_type="image/jpeg",
                    prompt=workflow_config.gemini_escalation_prompt,
                    model=model_name,
                )

            summary_text = (
                analysis.summary
                or analysis.description
                or "Routine aerial surveillance - zone clear."
            )

            logger.info(
                "Tier 2 [%s/%s] response for %s [TC %s]: latency=%.1fms | raw='%s' | summary='%s'",
                source_tier,
                source_model,
                self.config.drone_id,
                formatted_timecode or "N/A",
                analysis.latency_ms or 0.0,
                analysis.raw_response.strip() if analysis.raw_response else "",
                summary_text,
            )

            is_potential_threat = (
                analysis.suspicious_activity_detected or analysis.threat_level != ThreatLevel.NONE
            )
            threat_active = is_potential_threat and (
                analysis.confidence_score >= workflow_config.gemma_triage_threshold
            )

            if threat_active:
                self.config.status = StreamStatus.ALERT
                threat_level = analysis.threat_level
                category = analysis.category
                bounding_boxes = analysis.bounding_boxes
                logger.warning(
                    "DISPATCH ALERT from Drone %s [TC %s]: [%s] %s "
                    "(confidence=%.2f >= threshold=%.2f, source=%s/%s)",
                    self.config.drone_id,
                    formatted_timecode or "N/A",
                    threat_level,
                    summary_text,
                    analysis.confidence_score,
                    workflow_config.gemma_triage_threshold,
                    source_tier,
                    source_model,
                )
            else:
                self.config.status = StreamStatus.ONLINE
                threat_level = ThreatLevel.NONE
                category = IncidentCategory.CLEAR
                bounding_boxes = []
                if is_potential_threat:
                    logger.info(
                        "Suppressed below-threshold threat from Drone %s [TC %s]: [%s] %s "
                        "(confidence=%.2f < threshold=%.2f, source=%s/%s)",
                        self.config.drone_id,
                        formatted_timecode or "N/A",
                        analysis.threat_level,
                        summary_text,
                        analysis.confidence_score,
                        workflow_config.gemma_triage_threshold,
                        source_tier,
                        source_model,
                    )

            event = IncidentEvent(
                drone_id=self.config.drone_id,
                timestamp=datetime.now(UTC),
                location=Location(zone_name=self.config.zone_name),
                threat_level=threat_level,
                category=category,
                description=summary_text,
                confidence_score=analysis.confidence_score,
                bounding_boxes=bounding_boxes,
                snapshot_uri=None,
                video_timestamp_seconds=video_timestamp_sec,
                video_timestamp_formatted=formatted_timecode,
                source_tier=source_tier,
                source_model=source_model,
                model_name=analysis.model_name or model_name,
                scene_summary=summary_text,
                raw_response=analysis.raw_response,
                latency_ms=analysis.latency_ms,
            )

            if self.event_callback:
                await self.event_callback(event)
        except Exception as ex:
            logger.error("Error in background frame analysis task: %s", ex)

    async def _process_loop(self) -> None:
        """Main frame extraction and analysis loop."""
        active_analysis_tasks: set[asyncio.Task[None]] = set()
        max_concurrent_analysis: int = 3
        sample_interval: float = 1.0 / self.settings.frame_sampling_fps

        # Resolve GCS gs:// path to local cached file if needed
        local_video_path = self.config.stream_url
        if self.config.stream_url.startswith("gs://"):
            cached_path = await asyncio.to_thread(
                ensure_gcs_cached,
                self.config.stream_url,
                self.settings.gcp_project_id,
                self.settings.gcs_bucket_videos,
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

                            now_wall = time.time()
                            interval = self.settings.gemma_scene_description_interval_seconds
                            is_heartbeat = False
                            if (
                                frame_time - self._last_scene_description_time >= interval
                                or frame_time < self._last_scene_description_time
                                or (
                                    now_wall - self._last_scene_description_wall >= interval
                                    and self._last_scene_description_time < 0
                                )
                            ):
                                self._last_scene_description_time = frame_time
                                self._last_scene_description_wall = now_wall
                                is_heartbeat = True

                            # Run motion filter
                            has_motion, motion_score = self.motion_filter.process_frame(img_bgr)

                            success, buffer = cv2.imencode(".jpg", img_bgr)
                            if success:
                                frame_data = buffer.tobytes()
                                self.latest_frame_bytes = frame_data

                                if has_motion or is_heartbeat:
                                    active_analysis_tasks = {
                                        t for t in active_analysis_tasks if not t.done()
                                    }
                                    if len(active_analysis_tasks) < max_concurrent_analysis:
                                        task = asyncio.create_task(
                                            self._analyze_frame(
                                                frame_data, frame_time, is_heartbeat=is_heartbeat
                                            )
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
                            self._last_scene_description_time = -100.0
                        except Exception:
                            container.close()
                            container = av.open(local_video_path)
                            target_time = 0.0
                            self._last_scene_description_time = -100.0

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
                        interval = self.settings.gemma_scene_description_interval_seconds
                        is_heartbeat = False
                        if now - self._last_scene_description_wall >= interval:
                            self._last_scene_description_wall = now
                            is_heartbeat = True

                        has_motion, motion_score = self.motion_filter.process_frame(frame)
                        if has_motion or is_heartbeat:
                            active_analysis_tasks = {
                                t for t in active_analysis_tasks if not t.done()
                            }
                            if len(active_analysis_tasks) < max_concurrent_analysis:
                                task = asyncio.create_task(
                                    self._analyze_frame(
                                        frame_data, pos_sec, is_heartbeat=is_heartbeat
                                    )
                                )
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
