# DroneWatch 🛰️

**AI-Powered Multi-Drone Campus Surveillance & Real-Time Threat Detection System**

DroneWatch provides real-time AI-powered threat detection, multi-camera RTSP ingestion, motion-filtered video stream analysis, and instant dispatch alerting across campus surveillance networks.

---

### Architecture Overview

DroneWatch employs a **Hierarchical Two-Tier AI Inference Architecture** designed to maximize detection fidelity while reducing frontier multimodal LLM API consumption by up to 95%.

For complete architectural specifications, latency models, and formal Pydantic data contracts, see the comprehensive [Architecture Design Document](docs/ARCHITECTURE.md).

### Runtime Ingestion & Tiered AI Processing Flow

```
                               ┌─────────────────────────────────────────────────┐
                               │             Drone / IP RTSP Feeds               │
                               └────────────────────────┬────────────────────────┘
                                                        │ RTSP / MP4 Ingestion
                                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    FastAPI Ingestion & Serving Container                                │
│                                                                                                         │
│   ┌───────────────────────────┐      ┌─────────────────────────┐                                        │
│   │ OpenCV / PyAV Stream      ├─────►│ Tier 0: Motion Filter   │                                        │
│   │ Frame Decoders            │      │ (OpenCV Frame Diff)     │                                        │
│   └─────────────┬─────────────┘      └────────────┬────────────┘                                        │
│                 │                                 │ Motion Detected (>= 500 px)                         │
│                 │                                 ▼                                                     │
│                 │                    ┌─────────────────────────┐   Escalation Warranted                 │
│                 │                    │ Tier 1: Gemma 4         ├──────────────────────────┐             │
│                 │                    │ Triage (Cloud Run GPU)  │   (Threat Candidate)     │             │
│                 │                    └────────────┬────────────┘                          │             │
│                 │                                 │ Benign / Clear (< 0.50)              │             │
│                 │                                 ▼ (Dropped, 0 Gemini Cost)             │             │
│                 ▼                                                                        ▼             │
│   ┌───────────────────────────┐                                               ┌─────────────────────┐   │
│   │ MJPEG Streaming Endpoint  │                                               │ Tier 2: Gemini 3.6  │   │
│   │ GET /api/streams/{id}/video│                                              │ Flash (Vertex AI)   │   │
│   └───────────────────────────┘                                               └──────────┬──────────┘   │
│                                                                                          │ Validated    │
│                                                                                          │ Alert        │
│                                                                                          ▼              │
│                                                                               ┌─────────────────────┐   │
│                                                                               │ Real-time Alerts    │   │
│                                                                               │ WebSocket /ws/alerts│   │
│                                                                               └──────────┬──────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────────┼──────────────┘
                                                                                           │
                                                                                           ▼
                                                                                ┌─────────────────────┐
                                                                                │ React / Vite UI     │
                                                                                │ Real-Time Dashboard │
                                                                                └─────────────────────┘
```

---

## Production GCP Deployment Architecture

When deployed to Google Cloud Platform for production campus surveillance, DroneWatch leverages serverless containers, managed GPU inference, vector databases, and enterprise AI endpoints:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                               Google Cloud Project                                                 │
│                                                                                                                    │
│   ┌───────────────────────────────┐        ┌──────────────────────────────────────────────────────────┐            │
│   │ Client Browsers / IP Cameras  │        │ Artifact Registry (Docker Images)                        │            │
│   └───────────────┬───────────────┘        │ - dronewatch-backend:latest                              │            │
│                   │                        │ - dronewatch-gemma-triage:latest                         │            │
│                   ▼                        └──────────────┬───────────────────────────┬───────────────┘            │
│   ┌───────────────────────────────┐                       │                           │                            │
│   │ Cloud Run (Serverless)        │◄──────────────────────┘                           │                            │
│   │ dronewatch-backend            │                                                   │                            │
│   │ - FastAPI Ingestion Engine    │                                                   │                            │
│   │ - Embedded React SPA Bundle   │                                                   │                            │
│   │ - 2 vCPU / 4 GiB RAM          │                                                   │                            │
│   └──────┬────────────┬───────────┘                                                   │                            │
│          │            │                                                               │                            │
│          │ Direct VPC │ Internal VPC / HTTPS + IAM                                    │                            │
│          │ Egress     │ (Service Account OIDC Token)                                  │                            │
│          │            ▼                                                               │                            │
│          │   ┌─────────────────────────────────────────────────┐                      │                            │
│          │   │ Cloud Run: dronewatch-gemma-triage              │◄─────────────────────┘                            │
│          │   │ - Tier 1: Gemma 4 (google/gemma-4-E2B-it)       │                                                   │
│          │   │ - vLLM Serving + GCS FUSE Model Mount           │                                                   │
│          │   │ - 1x NVIDIA RTX Pro 6000 / L4 GPU (Scale-to-0)  │                                                   │
│          │   │ - Ingress: Internal Only (No Public IP)         │                                                   │
│          │   └────────┬────────────────────────────────────────┘                                                   │
│          │            │ Threat Candidate                                                                           │
│          │            │ Escalation                                                                                 │
│          │            ▼                                                                                            │
│          │   ┌─────────────────────────────────────────────────┐                                                   │
│          │   │ Vertex AI (locations/global)                    │                                                   │
│          │   │ Model: gemini-3.6-flash                         │                                                   │
│          │   │ Full contextual reasoning & bboxing             │                                                   │
│          │   └─────────────────────────────────────────────────┘                                                   │
│          ▼                                                                                                         │
│   ┌───────────────────────────────┐        ┌──────────────────────────────┐                                        │
│   │ AlloyDB for PostgreSQL        │        │ Cloud Storage (GCS)          │                                        │
│   │ - pgvector Extension          │        │ - <YOUR_GCP_PROJECT_ID>-videos│                                        │
│   │ - Incident Event Persistence  │        │ - <YOUR_GCP_PROJECT_ID>-snaps │                                        │
│   └───────────────────────────────┘        └──────────────────────────────┘                                        │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Managed GCP Services & Primitives

| Component | Service | Role & Responsibility |
|---|---|---|
| **Ingestion & Serving** | **Cloud Run (`dronewatch-backend`)** | Fully managed serverless container runtime hosting the FastAPI backend, RTSP stream ingestion, OpenCV motion gate, and compiled React SPA static bundle. Configured with `--min-instances=1` to eliminate cold-start delays on video streams. |
| **Tier 1 Vision Triage** | **Cloud Run GPU (`dronewatch-gemma-triage`)** | Internal microservice running Google's open vision-language model `gemma-4-E2B-it` via vLLM with GCS FUSE weight loading on a dedicated **NVIDIA GPU**. Scales to zero (`--min-instances=0`) when idle; protected by a fail-open circuit breaker on the backend. Rapidly screens candidate frames in ~40ms with IAM-authenticated private VPC ingress. |
| **Tier 2 Frontier AI** | **Vertex AI (`gemini-3.6-flash`)** | Multimodal reasoning engine under `locations/global`. Invoked strictly when Tier 1 detects suspicious or ambiguous activity. Performs deep policy evaluation, threat classification, bounding-box generation, and dispatch narrative formatting. |
| **Relational & Vector DB** | **AlloyDB for PostgreSQL** | High-performance PostgreSQL cluster with `pgvector` extension for storing incident logs, camera configurations, and vector embeddings for semantic security query retrieval. |
| **Container Management** | **Artifact Registry** | Secure Docker container repository hosting regional DroneWatch application builds (`us-central1-docker.pkg.dev/...`). |
| **Build Pipeline** | **Cloud Build** | Serverless CI/CD image compilation pipeline that packages Python dependencies (`uv`) and frontend React build artifacts into production containers. |
| **Network & Security** | **Direct VPC Egress & Internal Ingress** | Secure private VPC connectivity allowing Cloud Run container instances to communicate directly with AlloyDB private IP endpoints (`10.0.0.x`) and internal Gemma inference endpoints without public internet traversal. |
| **Object Storage** | **Cloud Storage (GCS)** | Object storage buckets for archiving raw MP4 surveillance footage, storing model weights (`jal-dronewatch-models`), and storing JPEG threat snapshot crops generated during security incidents. |

---

## Key Features & Component Design

### 1. Hierarchical Two-Tier AI Vision Pipeline
- **Tier 0 (Algorithmic Motion Filter):** OpenCV absolute frame differencing ($21 \times 21$ Gaussian blur, threshold $T=15$, $\ge 500\,\text{px}$ contour area) eliminates 75% of static frames on local CPU before invoking any neural network.
- **Tier 1 (Front-Line Gemma 4 Triage on Cloud Run):**
  - **Model:** `google/gemma-4-E2B-it` running on Cloud Run with a dedicated **NVIDIA GPU** (RTX Pro 6000 / L4) and vLLM OpenAI-compatible runtime.
  - **Scale-to-Zero (`--min-instances=0`):** Idle GPU instances terminate to eliminate compute costs when drones are grounded. Cold starts (~35s–45s) are seamlessly cushioned by the backend's fail-open circuit breaker to Gemini Flash.
  - **Latency:** ~35ms–50ms per active frame evaluation.
  - **Triage Gate:** Rapidly screens candidate frames for security relevance. Normal pedestrians, authorized vehicles on roads, and swaying foliage receive a low triage score (`< 0.50`) and are discarded without invoking external frontier APIs.
  - **Periodic Scene Description Heartbeat:** Unconditionally queries Gemma 4 every 10 seconds to generate a concise 15-word surveillance summary and operator HUD confirmation without writing benign entries to the database.
  - **Cost Impact:** Suppresses 93%–97% of motion-triggered frames from reaching Gemini, slashing frontier multimodal API costs by over 90%.
- **Tier 2 (Frontier Multimodal Reasoning via Gemini 3.6 Flash):**
  - **Model:** `gemini-3.6-flash` accessed via the Google GenAI SDK targeting `locations/global`.
  - **Escalation Trigger:** Invoked strictly when Tier 1 detects potential threats, hazards, or ambiguous security events (`triage_score >= 0.50`).
  - **Deep Contextual Validation:** Performs full spatial and policy reasoning, assesses severity levels (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), extracts normalized bounding boxes `[ymin, xmin, ymax, xmax]`, and formats dispatch-ready incident narratives.
  - **Structured Pydantic Outputs:** Strictly validated via Pydantic v2 schemas (`AnalysisResult`).

### 2. Dual Video Ingestion Engine
- **RTSP Live Feeds:** Decoded via OpenCV (`cv2.VideoCapture`) with low-buffer size flags (`CAP_PROP_BUFFERSIZE=1`) to eliminate buffering latency on live camera feeds.
- **GCS MP4 Files:** Local/remote MP4 files are demuxed using `PyAV` to cleanly handle multi-stream videos, attached-picture tracks, and accurate video timecode alignment (`MM:SS`). Remote GCS blobs (`gs://`) are automatically cached locally to `/tmp/gcs_cache` with automatic RAM recycling.
- **Continuous Live Preview:** MJPEG live video feeds update continuously at 30 FPS regardless of motion or AI inference state.

### 3. Real-Time Alert Dispatch & Dashboard
- **WebSockets:** The FastAPI server pushes real-time threat detection events (`IncidentEvent`) directly to connected frontend clients over `/ws/alerts`.
- **AlloyDB + pgvector Integration:** Confirmed incident events and spatial telemetry are persisted to AlloyDB for PostgreSQL with vector embeddings for retrospective semantic queries.
- **Frontend Error Resilience:** The React + Vite frontend (`StreamGrid`) features auto-retry logic with cache-busting on `<img className="video-player">` elements to seamlessly manage RTSP connection handshakes.

---

## Configuration & Environment Variables

Environment variables are loaded via `pydantic-settings` from `.env`:

| Variable | Default Value | Description |
|---|---|---|
| `DRONEWATCH_GCP_PROJECT_ID` | `dronewatch-project` | Google Cloud project ID for Vertex AI |
| `DRONEWATCH_GCP_LOCATION` | `global` | Vertex AI regional endpoint location |
| `DRONEWATCH_GEMINI_MODEL` | `gemini-3.6-flash` | Gemini model version for vision analysis |
| `DRONEWATCH_USE_VERTEX_AI` | `true` | Enable Vertex AI client initialization |
| `DRONEWATCH_ENABLE_TIER1_GEMMA` | `false` | Enable Tier 1 Gemma inference triage gate |
| `DRONEWATCH_GEMMA_SERVICE_URL` | `""` | Internal Cloud Run URL for Tier 1 triage |
| `DRONEWATCH_GEMMA_MODEL_NAME` | `google/gemma-4-E2B-it` | Target model identifier served by vLLM |
| `DRONEWATCH_GEMMA_TRIAGE_THRESHOLD` | `0.50` | Triage score cutoff for escalating to Gemini |
| `DRONEWATCH_GEMMA_TIMEOUT_SECONDS` | `2.0` | Maximum timeout before failing open to Gemini |
| `DRONEWATCH_GEMMA_TRIAGE_PROMPT` | `"detect campus security anomalies..."` | Zero-shot triage classification prompt |
| `DRONEWATCH_GEMMA_SCENE_DESCRIPTION_INTERVAL_SECONDS` | `10.0` | Cadence for routine surveillance telemetry |
| `DRONEWATCH_GEMMA_SCENE_DESCRIPTION_PROMPT` | `"Briefly describe this drone surveillance..."` | Prompt for 10s HUD scene heartbeat |
| `DRONEWATCH_FRAME_SAMPLING_FPS` | `1.0` | Target frame evaluation rate (frames/sec) |
| `DRONEWATCH_MOTION_SENSITIVITY_THRESHOLD` | `15.0` | OpenCV pixel delta intensity threshold |
| `DRONEWATCH_MIN_MOTION_AREA` | `500` | Minimum pixel contour area to trigger LLM evaluation |
| `DRONEWATCH_MAX_CONCURRENT_STREAMS` | `4` | Maximum parallel video ingestion streams |
| `DRONEWATCH_GCS_BUCKET_VIDEOS` | `dronewatch-videos-bucket` | GCS Bucket for video streams |
| `DRONEWATCH_GCS_BUCKET_SNAPSHOTS` | `dronewatch-snapshots-bucket` | GCS Bucket for alert snapshots |
| `DRONEWATCH_ALLOYDB_HOST` | `None` | AlloyDB PostgreSQL IP/Host |
| `DRONEWATCH_ALLOYDB_DATABASE` | `dronewatch_db` | AlloyDB Database Name |

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

##### Step A: Enable GCP APIs & Prepare Repository
```bash
# Enable required GCP APIs
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    aiplatform.googleapis.com \
    alloydb.googleapis.com \
    storage.googleapis.com \
    vpcaccess.googleapis.com

# Create Artifact Registry repository
gcloud artifacts repositories create dronewatch-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="DroneWatch Docker repository"
```

##### Step B: Deploy Tier 1 Gemma Triage Service to Cloud Run (GPU)
```bash
# Execute automated Gemma 4 triage deployment script (vLLM + GCS FUSE + NVIDIA GPU)
chmod +x scripts/deploy_gemma_triage.sh
./scripts/deploy_gemma_triage.sh

# Or deploy manually with Cloud Run Scale-to-Zero (--min-instances=0):
MODELS_BUCKET="jal-dronewatch-models"
PREBUILT_IMAGE="us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:gemma4"

gcloud beta run deploy dronewatch-gemma-triage \
    --image="${PREBUILT_IMAGE}" \
    --platform=managed \
    --region=us-central1 \
    --execution-environment=gen2 \
    --no-allow-unauthenticated \
    --cpu=20 \
    --memory=80Gi \
    --gpu=1 \
    --gpu-type=nvidia-rtx-pro-6000 \
    --no-gpu-zonal-redundancy \
    --no-cpu-throttling \
    --min-instances=0 \
    --max-instances=1 \
    --concurrency=64 \
    --timeout=600 \
    --add-volume="name=model-vol,type=cloud-storage,bucket=${MODELS_BUCKET},readonly=true" \
    --add-volume-mount="volume=model-vol,mount-path=/models" \
    --startup-probe="tcpSocket.port=8080,initialDelaySeconds=30,failureThreshold=20,timeoutSeconds=10,periodSeconds=15" \
    --command="vllm" \
    --args="serve,/models/gemma-4-E2B-it,--served-model-name=google/gemma-4-E2B-it,--enable-chunked-prefill,--enable-prefix-caching,--generation-config=auto,--dtype=bfloat16,--max-num-seqs=64,--gpu-memory-utilization=0.95,--port=8080,--host=0.0.0.0"
```

##### Step C: Deploy Ingestion Backend to Cloud Run
```bash
# Build frontend SPA bundle
(cd frontend && npm run build)

# Submit backend container build via Cloud Build
gcloud builds submit \
    --tag us-central1-docker.pkg.dev/<YOUR_GCP_PROJECT_ID>/dronewatch-repo/dronewatch-backend:latest .

# Deploy Ingestion Backend to Cloud Run with Direct VPC egress
GEMMA_URL=$(gcloud run services describe dronewatch-gemma-triage --region=us-central1 --format="value(status.url)")

gcloud run deploy dronewatch-backend \
    --image=us-central1-docker.pkg.dev/<YOUR_GCP_PROJECT_ID>/dronewatch-repo/dronewatch-backend:latest \
    --platform=managed \
    --region=us-central1 \
    --allow-unauthenticated \
    --network=dronewatch-vpc-prod \
    --subnet=dronewatch-subnet-us-central1-prod \
    --vpc-egress=private-ranges-only \
    --set-env-vars="DRONEWATCH_GCP_PROJECT_ID=<YOUR_GCP_PROJECT_ID>,DRONEWATCH_GCP_LOCATION=global,DRONEWATCH_GEMINI_MODEL=gemini-3.6-flash,DRONEWATCH_ENVIRONMENT=production,DRONEWATCH_ENABLE_TIER1_GEMMA=true,DRONEWATCH_GEMMA_SERVICE_URL=${GEMMA_URL},DRONEWATCH_GEMMA_MODEL_NAME=google/gemma-4-E2B-it" \
    --min-instances=1 \
    --cpu=2 \
    --memory=8Gi
```

##### Step D: Configure Service-to-Service IAM Permissions
```bash
# Grant backend service account permission to invoke Tier 1 Gemma triage service
BACKEND_SA="543569011042-compute@developer.gserviceaccount.com"

gcloud run services add-iam-policy-binding dronewatch-gemma-triage \
    --region=us-central1 \
    --member="serviceAccount:${BACKEND_SA}" \
    --role="roles/run.invoker"
```

---

## Observability & Cloud Logging

DroneWatch emits structured logs at `INFO` level for continuous auditing of Tier 1 Gemma vision triage and Tier 2 Gemini escalations without emitting raw multi-megabyte base64 JPEG blobs.

### Filter Queries in Cloud Logging Logs Explorer

To monitor real-time Gemma vision classifications, image understanding verdicts, and inference latencies:

```sql
resource.type="cloud_run_revision"
resource.labels.service_name="dronewatch-backend"
textPayload=~"Tier 1 Gemma vision triage"
```

Sample log entry emitted per evaluated frame:
```text
INFO: Tier 1 Gemma vision triage [drone-alpha]: prompt='detect campus security anomalies...' | response='SAFE' | verdict=BENIGN score=0.05 tags=['safe'] (latency=41.2ms)
```

To monitor periodic 10-second HUD scene telemetry:
```sql
resource.type="cloud_run_revision"
resource.labels.service_name="dronewatch-backend"
textPayload=~"HUD Telemetry Heartbeat"
```

To monitor Gemma Cloud Run vLLM GPU container access and scale-to-zero wakeups:
```sql
resource.type="cloud_run_revision"
resource.labels.service_name="dronewatch-gemma-triage"
```

> [!NOTE]
> **Cold Start Handling:** When `dronewatch-gemma-triage` scales to zero (`min-instances=0`), an incoming request during container cold start will encounter a brief delay (~35s–45s). The backend's resilient **fail-open circuit breaker** catches the HTTP timeout, immediately escalates the frame to Gemini 3.6 Flash without dropping surveillance, and logs a recovery notice once Gemma returns `200 OK`.

---

## Project Structure

```
dronewatch/
├── docs/
│   └── ARCHITECTURE.md               # Two-Tier Hierarchical AI Architecture Specification
├── frontend/                         # React + Vite frontend application
│   ├── src/
│   │   ├── components/               # UI Components (StreamGrid, Header, AlertLog)
│   │   └── App.jsx                   # Main React entry point
│   ├── package.json                  # Frontend dependencies
│   └── vite.config.js                # Vite dev server configuration
├── scripts/                          # Automated deployment scripts
│   ├── deploy_gcp.sh                 # Cloud Run Backend deployment script
│   └── deploy_gemma_triage.sh        # Cloud Run GPU Gemma 4 triage deployment script
├── src/dronewatch/                   # Core Python backend package
│   ├── db/                           # AlloyDB / local memory store implementations
│   ├── models/                       # Pydantic v2 schemas
│   │   ├── events.py                 # IncidentEvent & Alert contracts
│   │   └── triage.py                 # GemmaTriageRequest & Response models
│   ├── services/
│   │   ├── analyzer.py               # Gemini 3.6 Flash vision analyzer service
│   │   ├── gemma_client.py           # Tier 1 Gemma 4 vLLM triage client
│   │   ├── motion_filter.py          # OpenCV motion pre-filtering service
│   │   └── stream_processor.py       # RTSP & MP4 ingestion engine with tiered triage
│   ├── config.py                     # Application settings (pydantic-settings)
│   └── main.py                       # FastAPI REST API & WebSocket endpoints
├── tests/                            # Pytest test suite (36 tests)
│   ├── test_api.py                   # REST API and WebSocket tests
│   ├── test_analyzer.py              # Gemini analyzer tests
│   ├── test_events_model.py          # Pydantic schema validation tests
│   ├── test_gemma_client.py          # Gemma client unit tests (OIDC, triage, circuit breaker)
│   └── test_stream_processor_gemma.py # Stream processor tiered pipeline tests
├── pyproject.toml                    # Python project configuration (uv/ruff/pytest)
└── README.md                         # Project documentation
```
