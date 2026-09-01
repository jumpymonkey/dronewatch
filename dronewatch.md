# Product Requirement Document (PRD): DroneWatch

**Project Title:** DroneWatch — Real-Time Multi-Drone RTSP Surveillance & Gemini-Powered Analytics Platform  
**Document Version:** 1.0.0  
**Target File:** `dronewatch.md`  
**Date:** September 1, 2026  
**Status:** Approved / Draft for Development  

---

## 1. Executive Summary & Product Vision

### 1.1 Executive Summary
**DroneWatch** is an enterprise-grade web application designed for real-time security surveillance analytics and multi-drone flight oversight. As security operations increasingly rely on continuous aerial monitoring using autonomous or human-piloted drones, single operators are often overwhelmed when managing multiple simultaneous live feeds. DroneWatch solves this cognitive overload by bridging live video streaming (via RTSP) with Google Gemini's multimodal artificial intelligence. 

The application ingests live RTSP feeds from multiple drones, converts streams for web playback, runs continuous visual understanding using Google Gemini, stores timestamped structured analytics in a high-performance **Google Cloud AlloyDB** PostgreSQL database, and instantly pushes real-time urgent notifications to pilots when critical events (such as perimeter breaches, fires, unauthorized vehicles, or suspicious personnel) are detected.

Furthermore, DroneWatch features an integrated **RTSP Testing & Simulation Engine** that allows developers and security teams to convert local MP4 video files into simulated live RTSP streams to test and validate AI detection pipelines without launching physical drones.

---

## 2. Key Objectives & Target Personas

### 2.1 Core Objectives
1. **Reduce Operator Cognitive Load:** Enable a single drone pilot or security dispatcher to safely monitor 5+ live drone streams simultaneously.
2. **Automate Threat Detection:** Leverage Google Gemini to continuously analyze video streams for safety, security, and operational anomalies in real time.
3. **Sub-Second Urgent Alerting:** Deliver immediate visual and auditory alerts via WebSockets/SSE for critical events requiring pilot intervention.
4. **Structured & Searchable Historical Logs:** Store timestamped visual analytics in AlloyDB (with optional `pgvector` support) for post-incident audits and trend analysis.
5. **Hardware-Independent Testing:** Provide a seamless RTSP simulation utility to stream local video files (e.g., DJI MP4 footage) as live RTSP feeds for offline testing and demonstration.

### 2.2 Target Personas
* **Drone Pilot / Fleet Operator:** Responsible for flying or overseeing multiple automated flight paths. Needs instant visual cues when a specific drone detects a security or safety anomaly.
* **Security Operations Center (SOC) Analyst:** Reviews real-time perimeter feeds, filters historical threat events by severity, and generates post-patrol audit reports.
* **DevOps / AI Test Engineer:** Uses the simulation mode to benchmark Gemini inference latency, fine-tune prompts, and test system stability using archived flight footage.

---

## 3. High-Level Architecture & Technical Stack

```
+-----------------------------------------------------------------------------------+
|                                  DRONEWATCH SYSTEM                                |
+-----------------------------------------------------------------------------------+
|                                                                                   |
|  [ Live Drones / MP4 Video Files ]                                                |
|             |                                                                     |
|             v (RTSP Stream)                                                       |
|  +-----------------------------------+                                            |
|  | RTSP Ingestion & Simulation Engine | (MediaMTX / FFmpeg RTSP Server)            |
|  +-----------------------------------+                                            |
|        |                       |                                                  |
|        | (HLS / WebSockets)    | (Frame Extraction / Stream Chunks)               |
|        v                       v                                                  |
|  +------------------+    +---------------------------------+                      |
|  |  Frontend UI     |    |  Gemini AI Inference Pipeline   | (Google Gemini API)  |
|  |  (React/Vite)    |    +---------------------------------+                      |
|  +------------------+                    |                                        |
|        ^                                 v (Structured JSON Analytics)            |
|        |                         +---------------------------------+              |
|        +-------------------------|  Real-Time Event Dispatcher     |              |
|        |  WebSockets Alerts      +---------------------------------+              |
|        |                                 |                                        |
|        |                                 v (Timestamped Writes)                   |
|  +-----------------------------------------------------------------+              |
|  |                    Google Cloud AlloyDB Database                 |              |
|  +-----------------------------------------------------------------+              |
+-----------------------------------------------------------------------------------+
```

### 3.1 Recommended Technology Stack

| Layer | Component | Description / Technology |
| :--- | :--- | :--- |
| **Frontend UI** | Modern Web App | React, Vite, HTML5 Canvas/Video, TailwindCSS, Lucide Icons, WebSockets Client |
| **Backend Service** | API & Orchestration | Node.js (TypeScript) or Python (FastAPI) |
| **Video Processing** | RTSP & Transcoding | FFmpeg, MediaMTX (RTSP Server), WebRTC / HLS streaming bridge |
| **AI / Visual Engine**| Multimodal Analysis | Google Gemini 3.1 Flash Live (Multimodal Live API over WebSockets) |
| **Database** | Enterprise Relational DB | Google Cloud AlloyDB for PostgreSQL (with `pgvector` extension) |
| **Real-Time Transport**| Push Notifications | WebSockets (Socket.io) or Server-Sent Events (SSE) |
| **Testing / Simulator**| Video-to-RTSP Streamer | Built-in CLI/Docker container leveraging FFmpeg loops on local MP4s |

---

## 4. Feature Specifications

### Feature 1: RTSP Live Video Stream Connection & Management
* **Requirement:** Users must be able to input, save, test, and view live RTSP video stream URLs (e.g., `rtsp://192.168.1.100:554/live/stream1`).
* **Multi-Stream Support:** Ability to render a grid view of up to 8 simultaneous drone feeds in a single view with individual status indicators (Connected, Reconnecting, Disconnected, Alert Active).
* **Low-Latency Playback:** Transcode RTSP into browser-compatible streams (WebRTC or Low-Latency HLS) for real-time monitoring with sub-2-second streaming latency.
* **Stream Health Monitoring:** Track bitrates, dropped frames, and connection state. Automatically attempt reconnection if an RTSP feed drops.

### Feature 2: Gemini-Powered Live Video Analysis & Understanding (Hybrid Architecture)
* **Model Selection:** Uses **Google Gemini 3.1 Flash Live** via the Multimodal Live API (`BidiGenerateContent` over persistent WebSockets for low-latency live video stream understanding and structured JSON detection).
* **Dual-Tier Streaming Architecture:**
  * **Tier 1 (Background Multi-Stream Processing):** An RTSP worker decodes live feeds and extracts keyframes at 1–2 FPS or 3-second buffer clips, passing them to Gemini for structured JSON event extraction and AlloyDB writes.
  * **Tier 2 (Real-Time Gemini Live Session for Active Threats):** When a stream enters a `CRITICAL` or focused state, open a persistent Gemini Multimodal Live WebSocket session to provide sub-second continuous visual tracking and agentic function calls (e.g. triggering external siren webhooks).
* **Multimodal Prompting:** Send video frames/clips to Google Gemini with structured prompts tailored for security and drone surveillance:
  * **Threat Identification:** Detect intruders, perimeter breaches, fires, smoke, unflagged vehicles, hazardous materials, and fallen persons.
  * **Severity Scoring:** Classify detections as `LOW` (informational), `MEDIUM` (caution/anomaly), or `CRITICAL` (urgent threat requiring action).
  * **Structured JSON Output:** Request Gemini to return strict JSON matching defined schema contracts.
* **Context Preservation:** Pass previous analysis summary context to Gemini to maintain temporal continuity (e.g., "Person moving towards North Fence").

### Feature 3: Timestamped Data Persistence in AlloyDB
* **AlloyDB Integration:** Connect securely to a Google Cloud AlloyDB PostgreSQL instance using Cloud SQL Auth Proxy or IAM database authentication.
* **Schema Storage:** Write every analysis record with:
  * `event_id` (UUID)
  * `stream_id` & `drone_id`
  * `timestamp` (UTC microsecond precision)
  * `severity_level` (LOW, MEDIUM, CRITICAL)
  * `category` (Intrusion, Safety, Equipment, General)
  * `description` (Human-readable text generated by Gemini)
  * `bounding_boxes` (JSON array of coordinate bounds for visual overlays)
  * `raw_gemini_response` (JSONB)
  * `embedding_vector` (`vector` datatype for semantic natural language log queries)
* **High Performance Writing:** Asynchronous batching queue to ensure database writes never block the real-time processing thread.

### Feature 4: Real-Time UI Notification & Pilot Safety Dashboard
* **Urgent Critical Event Alerting:** When Gemini identifies a `CRITICAL` severity event:
  * Trigger immediate visual highlights (pulsing red borders on the affected video feed).
  * Play an audible alarm sound (with user mute/acknowledge toggle).
  * Display a persistent floating banner across the UI with quick-action buttons: "Acknowledge", "Focus Feed", and "Trigger Alarm/Return Home".
* **Multi-Drone Pilot Overview:**
  * Combined status drawer showing real-time threat activity streams.
  * Timeline scrub bar to jump back to exact timestamped video clips when alerts occurred.
  * Alert notification center with filters by drone name, severity, and time range.

### Feature 5: RTSP Simulator & Local Video Testing Suite
* **Video File Ingestion:** Allow users to select local MP4 files (e.g., test files located in `./videos/DJI_0104.MP4`, `./videos/S1001976.MP4`, etc.) from the server or web UI.
* **Looping RTSP Server:** Execute an integrated RTSP broadcaster (via MediaMTX or FFmpeg) that loops the selected video file continuously at native FPS as an RTSP endpoint (e.g., `rtsp://localhost:8554/sim/dji_0104`).
* **Seamless Testing Workflow:**
  1. User selects a local video from the UI test panel.
  2. Clicks "Launch Test RTSP Stream".
  3. System provisions the stream URL and auto-populates the connection field in the main monitoring grid.
  4. System runs Gemini analytics and AlloyDB writes identically to a physical drone feed.

---

## 5. System Data Schema (AlloyDB / PostgreSQL)

```sql
-- Extension enablement for vector search
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table 1: Drone Streams Registry
CREATE TABLE drone_streams (
    stream_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    drone_name VARCHAR(100) NOT NULL,
    rtsp_url VARCHAR(500) NOT NULL,
    status VARCHAR(20) DEFAULT 'INACTIVE', -- ACTIVE, INACTIVE, ERROR
    is_simulation BOOLEAN DEFAULT FALSE,
    source_file VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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
    bounding_boxes JSONB, -- Array of {label, box: [ymin, xmin, ymax, xmax]}
    raw_response JSONB,
    embedding vector(768), -- Optional embedding for semantic log search
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table 3: Urgent Notifications & Acknowledgments
CREATE TABLE urgent_alerts (
    alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID NOT NULL REFERENCES stream_analytics(event_id) ON DELETE CASCADE,
    stream_id UUID NOT NULL REFERENCES drone_streams(stream_id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    is_acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    notes TEXT
);

-- Indexes for performance and quick dashboard querying
CREATE INDEX idx_analytics_stream_time ON stream_analytics (stream_id, timestamp DESC);
CREATE INDEX idx_analytics_severity ON stream_analytics (severity) WHERE severity = 'CRITICAL';
CREATE INDEX idx_alerts_unack ON urgent_alerts (is_acknowledged) WHERE is_acknowledged = FALSE;
```

---

## 6. Non-Functional Requirements & Performance Targets

* **Latency Targets:**
  * RTSP Stream Playback Latency: $< 2.0$ seconds.
  * Gemini Frame Extraction to Analysis Result: $< 3.0$ seconds.
  * Critical Alert Websocket Broadcast to UI Render: $< 200$ ms.
* **Scalability:**
  * System must support up to 10 concurrent active RTSP feeds per backend processing instance.
  * AlloyDB must handle up to 100 write operations per second with low connection overhead.
* **Reliability & Resilience:**
  * Automatic graceful degradation: If Gemini API rate limits occur, fallback to lower frame sampling frequency without crashing streams.
  * Database reconnect retry loops with exponential backoff.
* **Security Compliance:**
  * Store database connection secrets in Google Secret Manager or environment variables.
  * Encrypt RTSP credentials in memory and transit.
  * Sanitize user input for test stream creation.

---

## 7. UI / UX Design Specifications

### 7.1 Layout Grid Structure
1. **Header / Top Bar:**
   * Global Connection Status indicator.
   * "Add RTSP Stream" & "Launch Test Simulator" modal triggers.
   * Global Mute / Sound Toggle for critical alarms.
   * Active Drone Count & Unacknowledged Alerts Badge.
2. **Main Workspace:**
   * **Multi-Drone Grid View:** Dynamic 1x1, 2x2, or 3x3 layout. Each grid cell features live video player, status tag, pilot quick actions, and pulsing red glow on CRITICAL alert.
   * **Focused Drone View (Single Mode):** Large high-resolution video stream with real-time Gemini bounding box overlay, live event feed sidebar, and historical clip timeline.
3. **Right Drawer (Live Activity Feed):**
   * Reverse-chronological timeline of Gemini analysis events across all streams.
   * Color-coded badge pills (`CRITICAL` in Red, `MEDIUM` in Yellow, `LOW` in Slate).
   * Filter controls (by Drone, Severity, or Search text).
4. **Bottom Bar / Notification Toast Banner:**
   * High-priority sticky banner that appears upon `CRITICAL` threat detection with one-click navigation to the affected drone stream.

---

## 8. Implementation Roadmap & Phases

### Phase 1: Ingestion & RTSP Simulation Setup (Sprint 1-2)
* Setup Node.js/Python backend with MediaMTX / FFmpeg integration.
* Implement the RTSP simulator endpoint to stream local MP4 files (e.g., `DJI_0104.MP4`).
* Build basic Web UI with RTSP connection manager and video player grid.

### Phase 2: Gemini AI Integration & Pipeline (Sprint 3-4)
* Implement continuous frame grabber module from live RTSP feeds.
* Integrate Google Gemini API using **Gemini 3.1 Flash Live** over persistent WebSocket sessions for low-latency live video stream understanding.
* Establish strict JSON schema output formatting for detection results and severity levels.

### Phase 3: AlloyDB Persistence & Real-time WebSockets (Sprint 5-6)
* Provision Google Cloud AlloyDB instance and apply database migration scripts.
* Implement backend database writer service for timestamped event logging.
* Build WebSocket notification engine for pushing real-time alerts to the React frontend.

### Phase 4: UI Polish, Alerting & End-to-End Testing (Sprint 7-8)
* Finalize Pilot Dashboard with visual and auditory critical notification alerts.
* Implement alert acknowledgment workflow and historical search drawer.
* Execute end-to-end simulation testing using stored drone test videos.

---

## 9. Deliverables Summary

1. `dronewatch.md` — Product Requirement Document (This document).
2. `schema.sql` — Database setup scripts for Google Cloud AlloyDB.
3. Architecture diagram and API contract documentation.
