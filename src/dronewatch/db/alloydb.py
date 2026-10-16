"""AlloyDB PostgreSQL storage manager with pgvector integration and local fallback."""

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from dronewatch.config import Settings
from dronewatch.models.events import IncidentCategory, IncidentEvent, ThreatLevel
from dronewatch.models.workflow_config import (
    DEFAULT_ALERT_KEYWORDS,
    DEFAULT_BENIGN_KEYWORDS,
    DEFAULT_GEMMA_ESCALATION_PROMPT,
    AmbiguityPolicy,
    EscalationTarget,
    WorkflowConfig,
)

logger = logging.getLogger(__name__)


class AlloyDBManager:
    """Manages connection pool to AlloyDB PostgreSQL instance with pgvector extension."""

    def __init__(self, settings: Settings) -> None:
        """Initialize AlloyDB manager settings.

        Args:
            settings: Global Pydantic settings instance.
        """
        self.settings: Settings = settings
        self._pool: asyncpg.Pool[Any] | None = None
        self._local_fallback_store: list[IncidentEvent] = []
        self._local_workflow_config: WorkflowConfig | None = None

    async def connect(self) -> None:
        """Establish asyncpg connection pool to AlloyDB."""
        if not self.settings.alloydb_host:
            logger.info("AlloyDB host not configured. Running in local memory fallback mode.")
            return

        try:
            self._pool = await asyncpg.create_pool(
                host=self.settings.alloydb_host,
                port=self.settings.alloydb_port,
                user=self.settings.alloydb_user,
                password=self.settings.alloydb_password,
                database=self.settings.alloydb_database,
                min_size=2,
                max_size=10,
                timeout=10.0,
            )
            logger.info("Successfully connected to AlloyDB pool at %s", self.settings.alloydb_host)
            await self._initialize_schema()
        except Exception as err:
            logger.warning(
                "Could not connect to AlloyDB pool (%s). Operating in fallback mode.",
                err,
            )
            self._pool = None

    async def _initialize_schema(self) -> None:
        """Execute DDL schema setup for AlloyDB including pgvector extension."""
        if not self._pool:
            return

        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE EXTENSION IF NOT EXISTS vector;
                CREATE TABLE IF NOT EXISTS incident_events (
                    event_id UUID PRIMARY KEY,
                    drone_id VARCHAR(64) NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    zone_name VARCHAR(128) NOT NULL,
                    latitude DOUBLE PRECISION NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL,
                    threat_level VARCHAR(32) NOT NULL,
                    category VARCHAR(64) NOT NULL,
                    description TEXT NOT NULL,
                    confidence_score DOUBLE PRECISION NOT NULL,
                    bounding_boxes JSONB NOT NULL,
                    snapshot_uri TEXT,
                    video_timestamp_seconds DOUBLE PRECISION,
                    video_timestamp_formatted VARCHAR(32),
                    acknowledged_by_pilot BOOLEAN DEFAULT FALSE,
                    description_vector vector(768),
                    source_tier VARCHAR(32) DEFAULT 'triage',
                    source_model VARCHAR(32) DEFAULT 'gemma',
                    model_name VARCHAR(64),
                    scene_summary TEXT,
                    raw_response TEXT,
                    latency_ms DOUBLE PRECISION
                );
                ALTER TABLE incident_events
                    ADD COLUMN IF NOT EXISTS source_tier VARCHAR(32) DEFAULT 'triage';
                ALTER TABLE incident_events
                    ADD COLUMN IF NOT EXISTS source_model VARCHAR(32) DEFAULT 'gemma';
                ALTER TABLE incident_events ADD COLUMN IF NOT EXISTS model_name VARCHAR(64);
                ALTER TABLE incident_events ADD COLUMN IF NOT EXISTS scene_summary TEXT;
                ALTER TABLE incident_events ADD COLUMN IF NOT EXISTS raw_response TEXT;
                ALTER TABLE incident_events ADD COLUMN IF NOT EXISTS latency_ms DOUBLE PRECISION;
                CREATE INDEX IF NOT EXISTS idx_incidents_ts ON incident_events(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_incidents_threat ON incident_events(threat_level);

                CREATE TABLE IF NOT EXISTS workflow_settings (
                    config_id VARCHAR(32) PRIMARY KEY DEFAULT 'active',
                    enable_tier1_gemma BOOLEAN NOT NULL DEFAULT TRUE,
                    gemma_triage_prompt TEXT NOT NULL,
                    gemma_triage_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.50,
                    escalation_target VARCHAR(16) NOT NULL DEFAULT 'GEMINI',
                    gemini_escalation_prompt TEXT NOT NULL,
                    gemma_escalation_prompt TEXT NOT NULL,
                    gemini_model VARCHAR(64) NOT NULL DEFAULT 'gemini-3.6-flash',
                    gemma_model VARCHAR(64) NOT NULL DEFAULT 'google/gemma-4-E2B-it',
                    gemma_service_url TEXT,
                    gemma_timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 2.0,
                    alert_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
                    benign_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
                    ambiguity_policy VARCHAR(32) NOT NULL DEFAULT 'FAIL_SAFE',
                    vllm_temperature DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    vllm_max_tokens INT NOT NULL DEFAULT 32,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_by VARCHAR(64) NOT NULL DEFAULT 'pilot-admin',
                    version INT NOT NULL DEFAULT 1,
                    CONSTRAINT chk_singleton
                        CHECK (config_id = 'active'),
                    CONSTRAINT chk_escalation_target
                        CHECK (escalation_target IN ('GEMINI', 'GEMMA')),
                    CONSTRAINT chk_threshold_range
                        CHECK (gemma_triage_threshold >= 0.0 AND gemma_triage_threshold <= 1.0)
                );

                ALTER TABLE workflow_settings
                    ADD COLUMN IF NOT EXISTS gemma_service_url TEXT,
                    ADD COLUMN IF NOT EXISTS gemma_timeout_seconds DOUBLE PRECISION
                        NOT NULL DEFAULT 2.0,
                    ADD COLUMN IF NOT EXISTS alert_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
                    ADD COLUMN IF NOT EXISTS benign_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
                    ADD COLUMN IF NOT EXISTS ambiguity_policy VARCHAR(32)
                        NOT NULL DEFAULT 'FAIL_SAFE',
                    ADD COLUMN IF NOT EXISTS vllm_temperature DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    ADD COLUMN IF NOT EXISTS vllm_max_tokens INT NOT NULL DEFAULT 32;

                CREATE TABLE IF NOT EXISTS workflow_settings_history (
                    history_id BIGSERIAL PRIMARY KEY,
                    version INT NOT NULL,
                    enable_tier1_gemma BOOLEAN NOT NULL,
                    gemma_triage_prompt TEXT NOT NULL,
                    gemma_triage_threshold DOUBLE PRECISION NOT NULL,
                    escalation_target VARCHAR(16) NOT NULL,
                    gemini_escalation_prompt TEXT NOT NULL,
                    gemma_escalation_prompt TEXT NOT NULL,
                    gemini_model VARCHAR(64) NOT NULL,
                    gemma_model VARCHAR(64) NOT NULL,
                    gemma_service_url TEXT,
                    gemma_timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 2.0,
                    alert_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
                    benign_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
                    ambiguity_policy VARCHAR(32) NOT NULL DEFAULT 'FAIL_SAFE',
                    vllm_temperature DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    vllm_max_tokens INT NOT NULL DEFAULT 32,
                    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    changed_by VARCHAR(64) NOT NULL
                );

                ALTER TABLE workflow_settings_history
                    ADD COLUMN IF NOT EXISTS gemma_service_url TEXT,
                    ADD COLUMN IF NOT EXISTS gemma_timeout_seconds DOUBLE PRECISION
                        NOT NULL DEFAULT 2.0,
                    ADD COLUMN IF NOT EXISTS alert_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
                    ADD COLUMN IF NOT EXISTS benign_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
                    ADD COLUMN IF NOT EXISTS ambiguity_policy VARCHAR(32)
                        NOT NULL DEFAULT 'FAIL_SAFE',
                    ADD COLUMN IF NOT EXISTS vllm_temperature DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    ADD COLUMN IF NOT EXISTS vllm_max_tokens INT NOT NULL DEFAULT 32;
                """)

            # Seed default configuration if active row does not exist
            row = await conn.fetchrow(
                "SELECT config_id FROM workflow_settings WHERE config_id = 'active'"
            )
            if not row:
                default_config = self._create_default_workflow_config()
                await conn.execute(
                    """
                    INSERT INTO workflow_settings (
                        config_id, enable_tier1_gemma, gemma_triage_prompt,
                        gemma_triage_threshold, escalation_target,
                        gemini_escalation_prompt, gemma_escalation_prompt,
                        gemini_model, gemma_model, gemma_service_url,
                        gemma_timeout_seconds, alert_keywords, benign_keywords,
                        ambiguity_policy, vllm_temperature, vllm_max_tokens,
                        updated_at, updated_by, version
                    ) VALUES (
                        'active', $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17, $18
                    )
                    ON CONFLICT (config_id) DO NOTHING
                    """,
                    default_config.enable_tier1_gemma,
                    default_config.gemma_triage_prompt,
                    default_config.gemma_triage_threshold,
                    str(default_config.escalation_target),
                    default_config.gemini_escalation_prompt,
                    default_config.gemma_escalation_prompt,
                    default_config.gemini_model,
                    default_config.gemma_model,
                    default_config.gemma_service_url,
                    default_config.gemma_timeout_seconds,
                    json.dumps(default_config.alert_keywords),
                    json.dumps(default_config.benign_keywords),
                    str(default_config.ambiguity_policy),
                    default_config.vllm_temperature,
                    default_config.vllm_max_tokens,
                    default_config.updated_at,
                    default_config.updated_by,
                    default_config.version,
                )

            # Migrate legacy default Gemma escalation prompt to structured JSON schema prompt
            await conn.execute(
                """
                UPDATE workflow_settings
                SET gemma_escalation_prompt = $1
                WHERE config_id = 'active'
                  AND (
                    gemma_escalation_prompt LIKE 'Analyze this drone security surveillance frame%'
                    OR LENGTH(gemma_escalation_prompt) < 300
                  )
                """,
                DEFAULT_GEMMA_ESCALATION_PROMPT,
            )

            logger.info("AlloyDB schema, vector extensions, and workflow settings verified.")

    async def log_incident(
        self, event: IncidentEvent, vector_embedding: list[float] | None = None
    ) -> None:
        """Persist an incident event into AlloyDB or local fallback memory store.

        Args:
            event: IncidentEvent model instance.
            vector_embedding: Optional 768-dim text embedding vector for semantic search.
        """
        if self._pool:
            try:
                boxes_json = json.dumps([box.model_dump() for box in event.bounding_boxes])
                vector_str = str(vector_embedding) if vector_embedding else None

                async with self._pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO incident_events (
                            event_id, drone_id, timestamp, zone_name, latitude, longitude,
                            threat_level, category, description, confidence_score,
                            bounding_boxes, snapshot_uri, video_timestamp_seconds,
                            video_timestamp_formatted, acknowledged_by_pilot, description_vector,
                            source_tier, source_model, model_name, scene_summary,
                            raw_response, latency_ms
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                            $17, $18, $19, $20, $21, $22
                        )
                        """,
                        event.event_id,
                        event.drone_id,
                        event.timestamp,
                        event.location.zone_name,
                        event.location.latitude,
                        event.location.longitude,
                        str(event.threat_level),
                        str(event.category),
                        event.description,
                        event.confidence_score,
                        boxes_json,
                        event.snapshot_uri,
                        event.video_timestamp_seconds,
                        event.video_timestamp_formatted,
                        event.acknowledged_by_pilot,
                        vector_str,
                        event.source_tier,
                        event.source_model,
                        event.model_name,
                        event.scene_summary,
                        event.raw_response,
                        event.latency_ms,
                    )
                logger.info("Logged incident %s to AlloyDB.", event.event_id)
                return
            except Exception as err:
                logger.error("Failed to insert event into AlloyDB: %s. Storing locally.", err)

        self._local_fallback_store.append(event)
        logger.info("Stored incident %s in local memory store.", event.event_id)

    save_incident = log_incident

    async def get_recent_incidents(
        self, limit: int = 50, threat_filter: ThreatLevel | None = None
    ) -> list[IncidentEvent]:
        """Fetch the most recent logged security incidents.

        Args:
            limit: Max records to return.
            threat_filter: Optional threat level filter.

        Returns:
            List of IncidentEvent models.
        """
        if self._pool:
            try:
                async with self._pool.acquire() as conn:
                    if threat_filter:
                        rows = await conn.fetch(
                            """
                            SELECT event_id, drone_id, timestamp, zone_name, latitude, longitude,
                                   threat_level, category, description, confidence_score,
                                   bounding_boxes, snapshot_uri, video_timestamp_seconds,
                                   video_timestamp_formatted, acknowledged_by_pilot,
                                   source_tier, source_model, model_name, scene_summary,
                                   raw_response, latency_ms
                            FROM incident_events
                            WHERE threat_level = $1
                            ORDER BY timestamp DESC
                            LIMIT $2
                            """,
                            str(threat_filter),
                            limit,
                        )
                    else:
                        rows = await conn.fetch(
                            """
                            SELECT event_id, drone_id, timestamp, zone_name, latitude, longitude,
                                   threat_level, category, description, confidence_score,
                                   bounding_boxes, snapshot_uri, video_timestamp_seconds,
                                   video_timestamp_formatted, acknowledged_by_pilot,
                                   source_tier, source_model, model_name, scene_summary,
                                   raw_response, latency_ms
                            FROM incident_events
                            ORDER BY timestamp DESC
                            LIMIT $1
                            """,
                            limit,
                        )
                    events: list[IncidentEvent] = []
                    for r in rows:
                        events.append(
                            IncidentEvent(
                                event_id=r["event_id"],
                                drone_id=r["drone_id"],
                                timestamp=r["timestamp"],
                                location={
                                    "zone_name": r["zone_name"],
                                    "latitude": r["latitude"],
                                    "longitude": r["longitude"],
                                },
                                threat_level=ThreatLevel(r["threat_level"]),
                                category=IncidentCategory(r["category"]),
                                description=r["description"],
                                confidence_score=r["confidence_score"],
                                bounding_boxes=json.loads(r["bounding_boxes"]),
                                snapshot_uri=r["snapshot_uri"],
                                video_timestamp_seconds=r["video_timestamp_seconds"],
                                video_timestamp_formatted=r["video_timestamp_formatted"],
                                acknowledged_by_pilot=r["acknowledged_by_pilot"],
                                source_tier=r["source_tier"] or "triage",
                                source_model=r["source_model"] or "gemma",
                                model_name=r["model_name"],
                                scene_summary=r["scene_summary"],
                                raw_response=r["raw_response"],
                                latency_ms=r["latency_ms"],
                            )
                        )
                    return events

            except Exception as err:
                logger.error("AlloyDB query failed (%s). Falling back to local store.", err)

        items = self._local_fallback_store
        if threat_filter:
            items = [ev for ev in items if ev.threat_level == threat_filter]
        return list(reversed(items[-limit:]))

    async def acknowledge_incident(self, event_id: UUID) -> bool:
        """Mark an incident as acknowledged by pilot.

        Args:
            event_id: UUID of incident.

        Returns:
            True if updated successfully.
        """
        if self._pool:
            try:
                async with self._pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE incident_events SET acknowledged_by_pilot = TRUE "
                        "WHERE event_id = $1",
                        event_id,
                    )
                return True
            except Exception as err:
                logger.error("Failed to acknowledge incident in AlloyDB: %s", err)

        for ev in self._local_fallback_store:
            if ev.event_id == event_id:
                ev.acknowledged_by_pilot = True
                return True
        return False

    def _create_default_workflow_config(self) -> WorkflowConfig:
        """Generate default workflow configuration from application settings."""
        return WorkflowConfig(
            enable_tier1_gemma=self.settings.enable_tier1_gemma,
            gemma_triage_prompt=self.settings.gemma_triage_prompt,
            gemma_triage_threshold=self.settings.gemma_triage_threshold,
            escalation_target=EscalationTarget.GEMINI,
            gemini_model=self.settings.gemini_model,
            gemma_model=self.settings.gemma_model_name,
            gemma_service_url=self.settings.gemma_service_url or None,
            gemma_timeout_seconds=self.settings.gemma_timeout_seconds,
            alert_keywords=list(DEFAULT_ALERT_KEYWORDS),
            benign_keywords=list(DEFAULT_BENIGN_KEYWORDS),
            ambiguity_policy=AmbiguityPolicy.FAIL_SAFE,
            vllm_temperature=0.0,
            vllm_max_tokens=32,
        )

    async def get_workflow_config(self) -> WorkflowConfig:
        """Fetch active workflow configuration from AlloyDB or local fallback."""
        if self._pool:
            try:
                async with self._pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        SELECT enable_tier1_gemma, gemma_triage_prompt, gemma_triage_threshold,
                               escalation_target, gemini_escalation_prompt, gemma_escalation_prompt,
                               gemini_model, gemma_model, gemma_service_url, gemma_timeout_seconds,
                               alert_keywords, benign_keywords, ambiguity_policy,
                               vllm_temperature, vllm_max_tokens,
                               updated_at, updated_by, version
                        FROM workflow_settings
                        WHERE config_id = 'active'
                        """
                    )
                    if row:
                        raw_alert = row["alert_keywords"]
                        alert_kw = (
                            json.loads(raw_alert) if isinstance(raw_alert, str) else raw_alert
                        )
                        raw_benign = row["benign_keywords"]
                        benign_kw = (
                            json.loads(raw_benign) if isinstance(raw_benign, str) else raw_benign
                        )

                        return WorkflowConfig(
                            enable_tier1_gemma=row["enable_tier1_gemma"],
                            gemma_triage_prompt=row["gemma_triage_prompt"],
                            gemma_triage_threshold=row["gemma_triage_threshold"],
                            escalation_target=EscalationTarget(row["escalation_target"]),
                            gemini_escalation_prompt=row["gemini_escalation_prompt"],
                            gemma_escalation_prompt=row["gemma_escalation_prompt"],
                            gemini_model=row["gemini_model"],
                            gemma_model=row["gemma_model"],
                            gemma_service_url=row["gemma_service_url"],
                            gemma_timeout_seconds=row["gemma_timeout_seconds"] or 2.0,
                            alert_keywords=alert_kw
                            if alert_kw is not None
                            else list(DEFAULT_ALERT_KEYWORDS),
                            benign_keywords=benign_kw
                            if benign_kw is not None
                            else list(DEFAULT_BENIGN_KEYWORDS),
                            ambiguity_policy=AmbiguityPolicy(
                                row["ambiguity_policy"] or AmbiguityPolicy.FAIL_SAFE
                            ),
                            vllm_temperature=row["vllm_temperature"]
                            if row["vllm_temperature"] is not None
                            else 0.0,
                            vllm_max_tokens=row["vllm_max_tokens"]
                            if row["vllm_max_tokens"] is not None
                            else 32,
                            updated_at=row["updated_at"],
                            updated_by=row["updated_by"],
                            version=row["version"],
                        )
            except Exception as err:
                logger.error("AlloyDB workflow config query failed (%s). Falling back.", err)

        if self._local_workflow_config is None:
            self._local_workflow_config = self._create_default_workflow_config()
        return self._local_workflow_config

    async def save_workflow_config(self, config: WorkflowConfig) -> WorkflowConfig:
        """Persist updated workflow configuration to AlloyDB and record history."""
        config.version += 1
        config.updated_at = datetime.now(UTC)

        if self._pool:
            try:
                async with self._pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute(
                            """
                            INSERT INTO workflow_settings (
                                config_id, enable_tier1_gemma, gemma_triage_prompt,
                                gemma_triage_threshold, escalation_target,
                                gemini_escalation_prompt, gemma_escalation_prompt,
                                gemini_model, gemma_model, gemma_service_url,
                                gemma_timeout_seconds, alert_keywords, benign_keywords,
                                ambiguity_policy, vllm_temperature, vllm_max_tokens,
                                updated_at, updated_by, version
                            ) VALUES (
                                'active', $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                                $11, $12, $13, $14, $15, $16, $17, $18
                            )
                            ON CONFLICT (config_id) DO UPDATE SET
                                enable_tier1_gemma = EXCLUDED.enable_tier1_gemma,
                                gemma_triage_prompt = EXCLUDED.gemma_triage_prompt,
                                gemma_triage_threshold = EXCLUDED.gemma_triage_threshold,
                                escalation_target = EXCLUDED.escalation_target,
                                gemini_escalation_prompt = EXCLUDED.gemini_escalation_prompt,
                                gemma_escalation_prompt = EXCLUDED.gemma_escalation_prompt,
                                gemini_model = EXCLUDED.gemini_model,
                                gemma_model = EXCLUDED.gemma_model,
                                gemma_service_url = EXCLUDED.gemma_service_url,
                                gemma_timeout_seconds = EXCLUDED.gemma_timeout_seconds,
                                alert_keywords = EXCLUDED.alert_keywords,
                                benign_keywords = EXCLUDED.benign_keywords,
                                ambiguity_policy = EXCLUDED.ambiguity_policy,
                                vllm_temperature = EXCLUDED.vllm_temperature,
                                vllm_max_tokens = EXCLUDED.vllm_max_tokens,
                                updated_at = EXCLUDED.updated_at,
                                updated_by = EXCLUDED.updated_by,
                                version = EXCLUDED.version
                            """,
                            config.enable_tier1_gemma,
                            config.gemma_triage_prompt,
                            config.gemma_triage_threshold,
                            str(config.escalation_target),
                            config.gemini_escalation_prompt,
                            config.gemma_escalation_prompt,
                            config.gemini_model,
                            config.gemma_model,
                            config.gemma_service_url,
                            config.gemma_timeout_seconds,
                            json.dumps(config.alert_keywords),
                            json.dumps(config.benign_keywords),
                            str(config.ambiguity_policy),
                            config.vllm_temperature,
                            config.vllm_max_tokens,
                            config.updated_at,
                            config.updated_by,
                            config.version,
                        )
                        await conn.execute(
                            """
                            INSERT INTO workflow_settings_history (
                                version, enable_tier1_gemma, gemma_triage_prompt,
                                gemma_triage_threshold, escalation_target,
                                gemini_escalation_prompt, gemma_escalation_prompt,
                                gemini_model, gemma_model, gemma_service_url,
                                gemma_timeout_seconds, alert_keywords, benign_keywords,
                                ambiguity_policy, vllm_temperature, vllm_max_tokens,
                                changed_at, changed_by
                            ) VALUES (
                                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                                $11, $12, $13, $14, $15, $16, $17, $18
                            )
                            """,
                            config.version,
                            config.enable_tier1_gemma,
                            config.gemma_triage_prompt,
                            config.gemma_triage_threshold,
                            str(config.escalation_target),
                            config.gemini_escalation_prompt,
                            config.gemma_escalation_prompt,
                            config.gemini_model,
                            config.gemma_model,
                            config.gemma_service_url,
                            config.gemma_timeout_seconds,
                            json.dumps(config.alert_keywords),
                            json.dumps(config.benign_keywords),
                            str(config.ambiguity_policy),
                            config.vllm_temperature,
                            config.vllm_max_tokens,
                            config.updated_at,
                            config.updated_by,
                        )
                logger.info("Saved workflow config version %d to AlloyDB.", config.version)
                self._local_workflow_config = config
                return config
            except Exception as err:
                logger.error(
                    "Failed to save workflow config in AlloyDB: %s. Using local store.",
                    err,
                )

        self._local_workflow_config = config
        return config

    async def reset_workflow_config(self) -> WorkflowConfig:
        """Reset workflow configuration to system defaults."""
        default_config = self._create_default_workflow_config()
        # Reset version counter if resetting
        current = await self.get_workflow_config()
        default_config.version = current.version
        return await self.save_workflow_config(default_config)

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("Closed AlloyDB connection pool.")
