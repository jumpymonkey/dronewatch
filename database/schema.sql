-- DroneWatch Database Schema DDL
-- Compatible with local PostgreSQL 16 (with pgvector) and Google Cloud AlloyDB for PostgreSQL

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop tables if re-initializing schema
DROP TABLE IF EXISTS urgent_alerts CASCADE;
DROP TABLE IF EXISTS stream_analytics CASCADE;
DROP TABLE IF EXISTS drone_streams CASCADE;

-- Table 1: Drone Streams Registry
CREATE TABLE drone_streams (
    stream_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    drone_name VARCHAR(100) NOT NULL,
    rtsp_url VARCHAR(500) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'INACTIVE' 
        CHECK (status IN ('ACTIVE', 'INACTIVE', 'RECONNECTING', 'ERROR')),
    is_simulation BOOLEAN NOT NULL DEFAULT FALSE,
    source_file VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table 2: Timestamped Gemini Analysis Findings
CREATE TABLE stream_analytics (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    stream_id UUID NOT NULL REFERENCES drone_streams(stream_id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'CRITICAL')),
    category VARCHAR(50) NOT NULL,
    summary TEXT NOT NULL,
    detailed_analysis TEXT,
    bounding_boxes JSONB DEFAULT '[]'::jsonb,
    raw_response JSONB NOT NULL,
    embedding vector(768),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table 3: Urgent Notifications & Acknowledgments
CREATE TABLE urgent_alerts (
    alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID NOT NULL REFERENCES stream_analytics(event_id) ON DELETE CASCADE,
    stream_id UUID NOT NULL REFERENCES drone_streams(stream_id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'CRITICAL',
    is_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for Query Optimization & Real-Time Dashboard Queries
CREATE INDEX idx_drone_streams_status ON drone_streams(status);
CREATE INDEX idx_analytics_stream_time ON stream_analytics(stream_id, timestamp DESC);
CREATE INDEX idx_analytics_severity ON stream_analytics(severity) WHERE severity = 'CRITICAL';
CREATE INDEX idx_alerts_unack ON urgent_alerts(is_acknowledged) WHERE is_acknowledged = FALSE;

-- HNSW Vector Index for Semantic Natural Language Search
CREATE INDEX idx_analytics_embedding ON stream_analytics 
USING hnsw (embedding vector_cosine_ops);
