# DroneWatch 🛰️

**AI-Powered Multi-Drone Campus Surveillance & Real-Time Threat Detection System**

DroneWatch provides real-time AI-powered threat detection, multi-camera RTSP ingestion, motion-filtered video stream analysis, and instant dispatch alerting across campus surveillance networks.

---

## Architecture Overview

### Runtime Ingestion & AI Processing Flow

```
                               ┌─────────────────────────────────────────────────┐
                               │             Drone / IP RTSP Feeds               │
                               └────────────────────────┬────────────────────────┘
                                                        │
                                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    FastAPI Backend Service                                       │
│                                                                                                 │
│   ┌───────────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────┐   │
│   │ OpenCV / PyAV Stream      ├─────►│ OpenCV Motion Filter    ├─────►│ Gemini 3.6 Flash    │   │
│   │ Frame Decoders            │      │ (Frame Differencing)    │      │ (Vertex AI Global)  │   │
│   └─────────────┬─────────────┘      └─────────────────────────┘      └──────────┬──────────┘   │
│                 │                                                                │              │
│                 ▼                                                                ▼              │
│   ┌───────────────────────────┐                                       ┌─────────────────────┐   │
│   │ MJPEG Streaming Endpoint  │                                       │ Real-time Alerts    │   │
│   │ GET /api/streams/{id}/video│                                      │ WebSocket /ws/alerts│   │
│   └───────────────────────────┘                                       └──────────┬──────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┼──────────────┘
                                                                                   │
                                                                                   ▼
                                                                        ┌─────────────────────┐
                                                                        │ React / Vite UI     │
                                                                        │ Real-Time Dashboard │
                                                                        └─────────────────────┘
```

---

## Production GCP Deployment Architecture

When deployed to Google Cloud Platform for production campus surveillance, DroneWatch leverages serverless containers, managed vector databases, and enterprise AI endpoints:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       Google Cloud Project                                             │
│                                                                                                        │
│   ┌───────────────────────────────┐        ┌──────────────────────────────┐                            │
│   │ Client Browsers / IP Cameras  │        │ Artifact Registry            │                            │
│   └───────────────┬───────────────┘        │ Docker Images                │                            │
│                   │                        └──────────────┬───────────────┘                            │
│                   ▼                                       │                                            │
│   ┌───────────────────────────────┐                       │                                            │
│   │ Cloud Run (Serverless)        │◄──────────────────────┘                                            │
│   │ - FastAPI Backend Container   │                                                                    │
│   │ - Embedded React SPA Bundle   │                                                                    │
│   │ - 2 vCPU / 4 GiB RAM          │                                                                    │
│   └──────┬────────────────┬───────┘                                                                    │
│          │                │                                                                            │
│          │ Direct VPC      │ HTTPS / gRPC                                                               │
│          │ Egress         ▼                                                                            │
│          │        ┌────────────────────────────────────────────────┐                                  │
│          │        │ Vertex AI (locations/global)                   │                                  │
│          │        │ Model: gemini-3.6-flash                        │                                  │
│          │        └────────────────────────────────────────────────┘                                  │
│          ▼                                                                                             │
│   ┌───────────────────────────────┐        ┌──────────────────────────────┐                            │
│   │ AlloyDB for PostgreSQL        │        │ Cloud Storage (GCS)          │                            │
│   │ - pgvector Extension          │        │ - <YOUR_GCP_PROJECT_ID>-videos│                            │
│   │ - Incident Event Persistence  │        │ - <YOUR_GCP_PROJECT_ID>-snaps │                            │
│   └───────────────────────────────┘        └──────────────────────────────┘                            │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Managed GCP Services & Primitives

| Component | Service | Role & Responsibility |
|---|---|---|
| **Compute & Serving** | **Cloud Run** | Fully managed serverless container runtime hosting the FastAPI backend and serving the compiled React SPA static bundle. Configured with `--min-instances=1` to eliminate cold-start delays on video streams. |
| **Vision Intelligence** | **Vertex AI** | Multi-modal vision analysis engine invoking `gemini-3.6-flash` under `locations/global`. Performs zero-shot object detection, threat scoring, bounding-box generation, and event summarization. |
| **Relational & Vector DB** | **AlloyDB for PostgreSQL** | High-performance PostgreSQL cluster with `pgvector` extension for storing incident logs, camera configurations, and vector embeddings for semantic security query retrieval. |
| **Container Management** | **Artifact Registry** | Secure Docker container repository hosting regional DroneWatch application builds (`us-central1-docker.pkg.dev/...`). |
| **Build Pipeline** | **Cloud Build** | Serverless CI/CD image compilation pipeline that packages Python dependencies (`uv`) and frontend React build artifacts into production containers. |
| **Network & Security** | **Direct VPC Egress** | Secure private VPC connectivity allowing Cloud Run container instances to communicate directly with AlloyDB private IP endpoints (`10.0.0.x`). |
| **Object Storage** | **Cloud Storage (GCS)** | Object storage buckets for archiving raw MP4 surveillance footage and storing JPEG threat snapshot crops generated during security incidents. |

---

## Key Features & Component Design

### 1. Multimodal GenAI Vision Analysis
- **Model Standard:** Strictly standardized on `gemini-3.6-flash` via the Google GenAI SDK.
- **Vertex AI Global Endpoint:** Invocations target `locations/global/publishers/google/models/gemini-3.6-flash` for high throughput and consistent regional availability.
- **Structured Pydantic Outputs:** All model outputs are validated through Pydantic v2 schemas (`AnalysisResult`) enforcing structured threat level classification (`NONE`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), categorical tagging, bounding box coordinates `[ymin, xmin, ymax, xmax]`, and concise dispatch summaries.

### 2. OpenCV Motion Pre-Filtering
- **Zero-Waste Inference:** To conserve API budget and reduce unnecessary compute, an OpenCV motion pre-filter (`MotionFilter`) processes all incoming frames.
- **Filtering Algorithm:**
  1. Converts frames to grayscale and applies a $21 \times 21$ Gaussian blur to eliminate sensor noise.
  2. Computes absolute frame differencing (`cv2.absdiff`) against the prior reference frame.
  3. Applies binary thresholding and contour detection (`cv2.findContours`).
  4. Only frames with contour areas exceeding `min_motion_area` (default: 500 px) trigger a `gemini-3.6-flash` evaluation.
- **Continuous Live Preview:** MJPEG live video feeds update continuously at 30 FPS regardless of motion state, decoupling UI video streaming from AI inference sampling.

### 3. Dual Video Ingestion Engine
- **RTSP Live Feeds:** Decoded via OpenCV (`cv2.VideoCapture`) with low-buffer size flags (`CAP_PROP_BUFFERSIZE=1`) to eliminate buffering latency on live camera feeds.
- **GCS MP4 Files:** Local/remote MP4 files are demuxed using `PyAV` to cleanly handle multi-stream videos, attached-picture tracks, and accurate video timecode alignment (`MM:SS`). Remote GCS blobs (`gs://`) are automatically cached locally to `/tmp/gcs_cache`.

### 4. Real-Time Alert Dispatch & Dashboard
- **WebSockets:** The FastAPI server pushes real-time threat detection events (`IncidentEvent`) directly to connected frontend clients over `/ws/alerts`.
- **Frontend Error Resilience:** The React + Vite frontend (`StreamGrid`) features auto-retry logic with cache-busting on `<img className="video-player">` elements to seamlessly manage RTSP connection handshakes.

---

## Configuration & Environment Variables

Environment variables are loaded via `pydantic-settings` from `.env`:

| Variable | Default Value | Description |
|---|---|---|
| `DRONEWATCH_GCP_PROJECT_ID` | `<YOUR_GCP_PROJECT_ID>` | Google Cloud project ID for Vertex AI |
| `DRONEWATCH_GCP_LOCATION` | `global` | Vertex AI regional endpoint location |
| `DRONEWATCH_GEMINI_MODEL` | `gemini-3.6-flash` | Gemini model version for vision analysis |
| `DRONEWATCH_USE_VERTEX_AI` | `true` | Enable Vertex AI client initialization |
| `DRONEWATCH_FRAME_SAMPLING_FPS` | `1.0` | Target frame evaluation rate (frames/sec) |
| `DRONEWATCH_MOTION_SENSITIVITY_THRESHOLD` | `15.0` | OpenCV pixel delta intensity threshold |
| `DRONEWATCH_MIN_MOTION_AREA` | `500` | Minimum pixel contour area to trigger LLM evaluation |
| `DRONEWATCH_MAX_CONCURRENT_STREAMS` | `4` | Maximum parallel video ingestion streams |

---

## Development & Deployment Guide

### Local Development & Testing

#### Prerequisites
- Python 3.12+
- `uv` package manager
- Node.js 20+

```bash
# Sync virtual environment and dependencies
uv sync

# Run static analysis and linting
uv run ruff check .
uv run ruff format --check .

# Run unit and integration test suite
uv run pytest

# Launch FastAPI backend locally (Port 8000)
uv run uvicorn dronewatch.main:app --host 0.0.0.0 --port 8000 --reload

# Launch Vite frontend dev server (Port 3000, in frontend/)
cd frontend && npm run dev -- --host 0.0.0.0 --port 3000
```

---

### Production Deployment to Google Cloud Platform

#### 1. Pre-Deployment Setup
Ensure you have the `gcloud` CLI installed and authenticated:

```bash
gcloud auth login
gcloud config set project <YOUR_GCP_PROJECT_ID>
```

#### 2. Automated GCP Deployment Script
Run the automated deployment script provided in `scripts/deploy_gcp.sh`:

```bash
export GCP_PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
export GCP_REGION="us-central1"
export ALLOYDB_HOST="<YOUR_ALLOYDB_IP>"
export ALLOYDB_PASSWORD="<YOUR_ALLOYDB_PASSWORD>"

chmod +x scripts/deploy_gcp.sh
./scripts/deploy_gcp.sh
```

#### 3. Manual Step-by-Step Cloud Run Deployment

If you prefer to deploy manually:

```bash
# 1. Enable required GCP APIs
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    aiplatform.googleapis.com \
    alloydb.googleapis.com \
    storage.googleapis.com \
    vpcaccess.googleapis.com

# 2. Create Artifact Registry repository
gcloud artifacts repositories create dronewatch-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="DroneWatch Docker repository"

# 3. Build frontend SPA bundle
(cd frontend && npm run build)

# 4. Submit Container Build via Cloud Build
gcloud builds submit \
    --tag us-central1-docker.pkg.dev/<YOUR_GCP_PROJECT_ID>/dronewatch-repo/dronewatch-backend:latest .

# 5. Deploy Container to Cloud Run
gcloud run deploy dronewatch-backend \
    --image=us-central1-docker.pkg.dev/<YOUR_GCP_PROJECT_ID>/dronewatch-repo/dronewatch-backend:latest \
    --platform=managed \
    --region=us-central1 \
    --allow-unauthenticated \
    --network=dronewatch-vpc-prod \
    --subnet=dronewatch-subnet-us-central1-prod \
    --vpc-egress=all-traffic \
    --set-env-vars="DRONEWATCH_GCP_PROJECT_ID=<YOUR_GCP_PROJECT_ID>,DRONEWATCH_GCP_LOCATION=global,DRONEWATCH_GEMINI_MODEL=gemini-3.6-flash,DRONEWATCH_ENVIRONMENT=production" \
    --min-instances=1 \
    --cpu=2 \
    --memory=4Gi
```

---

## Project Structure

```
dronewatch/
├── frontend/                     # React + Vite frontend application
│   ├── src/
│   │   ├── components/           # UI Components (StreamGrid, Header, AlertLog)
│   │   └── App.jsx               # Main React entry point
│   ├── package.json              # Frontend dependencies
│   └── vite.config.js            # Vite dev server configuration
├── scripts/                      # Deployment scripts
│   └── deploy_gcp.sh             # GCP Cloud Run & Artifact Registry deployment script
├── src/dronewatch/               # Core Python backend package
│   ├── db/                       # AlloyDB / local memory store implementations
│   ├── models/                   # Pydantic v2 schemas for events and stream configs
│   ├── services/
│   │   ├── analyzer.py           # Gemini 3.6 Flash vision analyzer service
│   │   ├── motion_filter.py      # OpenCV motion pre-filtering service
│   │   └── stream_processor.py   # RTSP and MP4 stream ingestion processor
│   ├── config.py                 # Application settings (pydantic-settings)
│   └── main.py                   # FastAPI REST API and WebSocket endpoints
├── tests/                        # Pytest suite
│   ├── test_api.py               # REST API and WebSocket tests
│   ├── test_analyzer.py          # Gemini analyzer tests
│   └── test_events_model.py      # Pydantic schema validation tests
├── pyproject.toml                # Python project configuration (uv/ruff/pytest)
└── README.md                     # Project documentation
```
