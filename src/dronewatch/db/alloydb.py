"""AlloyDB PostgreSQL storage manager with pgvector integration and local fallback."""

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

from dronewatch.config import Settings
from dronewatch.models.events import IncidentCategory, IncidentEvent, ThreatLevel

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
                    description_vector vector(768)
                );
                CREATE INDEX IF NOT EXISTS idx_incidents_ts ON incident_events(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_incidents_threat ON incident_events(threat_level);
                """)
            logger.info("AlloyDB schema and vector extensions verified.")

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
                            video_timestamp_formatted, acknowledged_by_pilot, description_vector
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
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
                                   video_timestamp_formatted, acknowledged_by_pilot
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
                                   video_timestamp_formatted, acknowledged_by_pilot
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

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("Closed AlloyDB connection pool.")
