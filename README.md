# DroneWatch 🛰️

**AI-Powered Multi-Drone Campus Surveillance & Real-Time Threat Detection System**

DroneWatch provides real-time AI-powered threat detection, multi-camera RTSP ingestion, motion-filtered video stream analysis, and instant dispatch alerting across campus surveillance networks.

---

## What's New in v3.0: System 1 Decision Framework

Version 3.0 replaces single-frame keyword string matching and unbounded Tier 2 queuing with **calibrated probability math, temporal noise rejection, and deterministic latency protection**—at zero additional GPU or Vertex AI cost:

| Dimension | Old v2.2 Gemma 4 Triage | New v3.0 System 1 Decision Framework | Operational Gain |
|---|---|---|---|
| **Confidence Signal** | Step-function buckets (`0.05`, `0.20`, `0.80`, `0.90`) guessed from free-form text | Exact softmax over vLLM `top_logprobs` + normalized Shannon entropy in [`gemma_client.py`](src/dronewatch/services/gemma_client.py) | **Sliders actually work:** setting `0.35` vs. `0.65` in [`AdminView.jsx`](frontend/src/components/AdminView.jsx) tunes continuous calibrated probabilities instead of dead zones. |
| **Tier 1 Speed** | Generated up to `32` free-text tokens (~35ms–55ms) | Constrained 1-token choice (`SAFE` \| `SUSPICIOUS` \| `CRITICAL`) (~15ms–25ms) | **~2x faster Tier 1 decode** and higher concurrent stream headroom on the same GPU. |
| **Negation & Language Bugs** | Substring matching (`"no hazards"` matched `"hazard"` → false `0.90` escalation) | Constrained token choice + clause-scoped `_strip_negated_clauses()` fallback | **Eliminates false Gemini bills** triggered by benign negated descriptions. |
| **1-Frame Transients** | Memoryless frame-by-frame binary gate | 3-band routing + `O(1)` `2-of-3` ring buffer in [`decision_engine.py`](src/dronewatch/services/decision_engine.py) | **Filters wind, shadow, and motion-blur spikes** in Band 1 while still escalating clear threats (`Band 2` / `CRITICAL`) on frame 1. |
| **Sustained Activity (Snowball Risk)** | Every frame ≥ threshold fired a parallel ~900ms Gemini call; out-of-order responses could overwrite newer HUD state | Single-flight lock, `3.0s` cooldown (`COOLDOWN_SKIP`), and monotonic watermarks (`STALE_WATERMARK_DROPPED`) in [`stream_processor.py`](src/dronewatch/services/stream_processor.py) | **Zero latency snowballing** and **60%–75% fewer redundant Gemini calls** when an incident stays in view across multiple seconds. |
| **Screening vs. Siren Policy** | Single shared `gemma_triage_threshold` controlled both Tier 1 escalation and Tier 2 sirens | Decoupled `suppress_threshold`, `gemma_triage_threshold`, and `dispatch_confidence_threshold` in [`workflow_config.py`](src/dronewatch/models/workflow_config.py) | **High recall without false alarms:** cast a wide net at Tier 1 (e.g., `0.40`) while requiring high certainty at Tier 2 (e.g., `0.75`) before paging operators. |
| **Auditability** | Logged raw text + pass/fail only | Persists `routing_action` and `dispatch_action` per event in [`alloydb.py`](src/dronewatch/db/alloydb.py) and Live AI Telemetry | **Instant root-cause visibility** into *why* any frame was suppressed, held for corroboration, shed by cooldown, or dispatched. |

---

### Architecture Overview (v3.0 System 1 Decision Framework)

DroneWatch v3.0 employs a **System 1 Decision Framework & Two-Tier Cascade Architecture** designed to maximize detection fidelity, eliminate keyword-negation false positives, guarantee non-cascading frame latency, and reduce frontier multimodal LLM API consumption by up to 95%.

For complete mathematical specifications (softmax `top_logprobs` calibration & Shannon entropy), anti-snowball backpressure guarantees, and formal Pydantic data contracts, see the comprehensive [Architecture Design Document](docs/ARCHITECTURE.md).

### Runtime Ingestion & System 1 Decision Flow

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
│                 │                    ┌─────────────────────────┐                                        │
│                 │                    │ Tier 1: Gemma 4 (vLLM)  │  Constrained 1-Token Choice            │
│                 │                    │ SAFE|SUSPICIOUS|CRITICAL│  + Softmax top_logprobs (~20ms)        │
│                 │                    └────────────┬────────────┘                                        │
│                 │                                 ▼                                                     │
│                 │                    ┌──────────────────────────────────────┐                           │
│                 │                    │ Deterministic DecisionEngine         │                           │
│                 │                    │ - Band 0 (< 0.25): SUPPRESS (0 Cost) │                           │
│                 │                    │ - Band 1 (0.25–0.50): O(1) k-of-n    │                           │
│                 │                    │ - Band 2 (>= 0.50): ESCALATE         │                           │
│                 │                    │ - Single-Flight Lock + 3.0s Cooldown │                           │
│                 │                    └───────────────────┬──────────────────┘                           │
│                 ▼                                        │ Corroborated / Immediate Escalation          │
│   ┌───────────────────────────┐                          ▼                                              │
│   │ MJPEG Streaming Endpoint  │              ┌──────────────────────────────┐                           │
│   │ GET /api/streams/{id}/video│             │ Tier 2: Deep Reasoning       │                           │
│   └───────────────────────────┘              │ Gemini Flash (Vertex AI) OR  │                           │
│                                              │ Gemma 4 / DiffusionGemma     │                           │
│                                              └──────────────┬───────────────┘                           │
│                                                             │ Decoupled Dispatch Policy                 │
│                                                             │ + Monotonic Timestamp Watermark           │
│                                                             ▼                                           │
│                                              ┌──────────────────────────────┐                           │
│                                              │ Real-Time Validated Alerts   │                           │
│                                              │ WebSocket /ws/alerts + DB    │                           │
│                                              └──────────────┬───────────────┘                           │
└─────────────────────────────────────────────────────────────┼───────────────────────────────────────────┘
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
│   │ - FastAPI + DecisionEngine    │                                                   │                            │
│   │ - Embedded React SPA Bundle   │                                                   │                            │
│   │ - 2 vCPU / 4–8 GiB RAM        │                                                   │                            │
│   └──────┬────────────┬───────────┘                                                   │                            │
│          │            │                                                               │                            │
│          │ Direct VPC │ Internal VPC / HTTPS + IAM                                    │                            │
│          │ Egress     │ (Service Account OIDC Token)                                  │                            │
│          │            ▼                                                               │                            │
│          │   ┌─────────────────────────────────────────────────┐                      │                            │
│          │   │ Cloud Run: dronewatch-gemma-triage              │◄─────────────────────┘                            │
│          │   │ - Tier 1: Gemma 4 (google/gemma-4-E2B-it)       │                                                   │
│          │   │ - vLLM guided_choice + top_logprobs + GCS FUSE  │                                                   │
│          │   │ - 1x NVIDIA RTX Pro 6000 (20 vCPU / 80 GiB)     │                                                   │
│          │   │ - Ingress: Internal Only (Scale-to-Zero)        │                                                   │
│          │   └────────┬────────────────────────────────────────┘                                                   │
│          │            │ Corroborated / Immediate                                                                   │
│          │            │ Threat Candidate                                                                           │
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
│   │ - Incident & Decision Audit   │        │ - <YOUR_GCP_PROJECT_ID>-snaps │                                        │
│   └───────────────────────────────┘        └──────────────────────────────┘                                        │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Managed GCP Services & Primitives

| Component | Service | Role & Responsibility |
|---|---|---|
| **Ingestion & Decision Engine** | **Cloud Run (`dronewatch-backend`)** | Serverless runtime hosting FastAPI, RTSP/MP4 ingestion, OpenCV motion gate, deterministic `DecisionEngine`, and compiled React SPA bundle (`--min-instances=1`). |
| **Tier 1 System 1 Triage** | **Cloud Run GPU (`dronewatch-gemma-triage`)** | Internal microservice running `google/gemma-4-E2B-it` via vLLM (`guided_choice` + `top_logprobs`) with GCS FUSE weight loading on an **NVIDIA RTX Pro 6000** (or parameterized L4). Scales to zero (`--min-instances=0`) when idle; protected by a fail-open circuit breaker. |
| **Tier 2 Deep Reasoning** | **Vertex AI (`gemini-3.6-flash`) / Cloud Run GPU** | Invoked strictly on corroborated Band 1 or immediate Band 2 candidates. Supports Vertex AI Gemini models or self-hosted vLLM (`google/gemma-4-E2B-it` / `google/diffusiongemma-26B-A4B-it`). |
| **Relational & Vector DB** | **AlloyDB for PostgreSQL** | PostgreSQL cluster with `pgvector` storing incident events, `routing_action` / `dispatch_action` audit trails, and hot-reloaded `workflow_settings`. |
| **Container Management** | **Artifact Registry** | Regional Docker repository hosting DroneWatch builds (`us-central1-docker.pkg.dev/...`). |
| **Build Pipeline** | **Cloud Build** | Serverless CI/CD image compilation packaging Python dependencies (`uv`) and React SPA build artifacts. |
| **Network & Security** | **Direct VPC Egress & Internal Ingress** | Private VPC connectivity to AlloyDB (`10.0.0.x`) and IAM-authenticated internal vLLM triage endpoints with zero public egress for raw triage frames. |
| **Object Storage** | **Cloud Storage (GCS)** | Buckets for archived MP4 streams, model weights (`jal-dronewatch-models`), and JPEG incident snapshots. |

---

## Key Features & Component Design

### 1. System 1 Decision Framework & Two-Tier Vision Cascade (v3.0)
- **Tier 0 (Algorithmic Motion Filter):** OpenCV absolute frame differencing ($21 \times 21$ Gaussian blur, threshold $T=15$, $\ge 500\,\text{px}$ contour area) eliminates ~75% of static frames on local CPU in ~2ms.
- **Tier 1 (Calibrated Gemma 4 Triage on Cloud Run GPU):**
  - **Constrained Logprob Calibration:** Executes single-token constrained decoding (`guided_choice=["SAFE", "SUSPICIOUS", "CRITICAL"]`, `top_logprobs=10`) on `google/gemma-4-E2B-it` in ~15ms–25ms. Exact softmax normalization produces calibrated threat probability $P(\text{threat}) = P(\text{SUSPICIOUS}) + P(\text{CRITICAL})$ and normalized Shannon entropy $H_{\text{norm}} \in [0, 1]$.
  - **Automatic Fallback & Negation Safety:** Gracefully retries without `guided_choice` if a custom OpenAI-compatible server returns HTTP 400/422, applying clause-scoped negation stripping (`"walkway is clear without hazards"` $\to$ `SAFE`, while `"no fire, but intruder climbing fence"` $\to$ `ALERT`).
  - **3-Band Deterministic Routing (`DecisionEngine`):**
    - **Band 0 (`P(threat) < suppress_threshold`, default `0.25`):** `SUPPRESS` immediately at zero API cost.
    - **Band 1 (`0.25 <= P(threat) < 0.50` or high entropy):** `CORROBORATE_HOLD` / `ESCALATE_CORROBORATED` using a non-blocking $O(1)$ per-stream `k-of-n` (`2-of-3`) ring buffer.
    - **Band 2 (`P(threat) >= gemma_triage_threshold`, default `0.50`, or `CRITICAL`):** `ESCALATE_IMMEDIATE` on the first frame.
  - **Anti-Snowball Backpressure Guarantees:** Prevents Tier 2 latency cascades via non-sleeping ring buffers, per-stream single-flight Tier 2 locks (`tier2_in_flight`), configurable non-`CRITICAL` escalation cooldowns (`3.0s` default), and monotonic video timestamp watermarks (`STALE_WATERMARK_DROPPED`).
  - **10-Second HUD Heartbeat:** Unconditionally queries Gemma 4 every 10s for a <15-word operator patrol summary streamed directly over WebSockets without AlloyDB write amplification.
- **Tier 2 (Frontier Multimodal Reasoning & Decoupled Dispatch):**
  - **Model Agility:** Escalates to `gemini-3.6-flash` on Vertex AI (with selectable `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-4-aragon`) or self-hosted Gemma 4 / `google/diffusiongemma-26B-A4B-it` (parallel block-denoising MoE for fast structured JSON).
  - **Decoupled Dispatch Policy:** Supports an independent `dispatch_confidence_threshold` so operators can keep Tier 1 screening sensitive while requiring high confidence before sounding HUD sirens.

### 2. Dual Video Ingestion Engine
- **RTSP Live Feeds:** Decoded via OpenCV (`cv2.VideoCapture`) with low-buffer size flags (`CAP_PROP_BUFFERSIZE=1`) to eliminate buffering latency on live camera feeds.
- **GCS MP4 Files:** Local/remote MP4 files are demuxed using `PyAV` to cleanly handle multi-stream videos, attached-picture tracks, and accurate video timecode alignment (`MM:SS`). Remote GCS blobs (`gs://`) are automatically cached locally to `/tmp/gcs_cache` with automatic RAM recycling.
- **Continuous Live Preview:** MJPEG live video feeds update continuously at 30 FPS regardless of motion or AI inference state.

### 3. Real-Time Alert Dispatch & Dashboard
- **WebSockets:** The FastAPI server pushes real-time threat detection events (`IncidentEvent`) directly to connected frontend clients over `/ws/alerts`.
- **AlloyDB + pgvector Integration:** Confirmed incident events, decision routing/dispatch actions, and spatial telemetry are persisted to AlloyDB for PostgreSQL with vector embeddings for semantic retrieval.
- **Frontend Error Resilience:** The React + Vite frontend (`StreamGrid`) features auto-retry logic with cache-busting on `<img className="video-player">` elements to seamlessly manage RTSP connection handshakes.

### 4. Dynamic Workflow Administration Console (`AdminView.jsx`)
- **Hot-Reloaded System 1 Controls:** Switch live between `DECISION_FRAMEWORK` (vLLM logprobs) and `KEYWORD_LEGACY`, tune Band 0 (`suppress_threshold`) and Band 2 (`gemma_triage_threshold`) sliders, adjust `k-of-n` corroboration depth (`corroboration_hits` / `corroboration_window`), and configure the `escalation_cooldown_seconds` anti-snowball window.
- **Independent Tier 2 Cutoff:** Toggle an independent `dispatch_confidence_threshold` or inherit the Tier 1 Band 2 cutoff.
- **Model & Runtime Selectors:** Select Vertex AI Gemini models or vLLM Gemma models (including `google/gemma-4-E2B-it` and `google/diffusiongemma-26B-A4B-it`), tune temperature/max tokens/timeouts, edit alert/benign keyword chips, and inspect `routing_action` / `dispatch_action` traces in the Live AI Telemetry log.
- **AlloyDB Persistence & Versioning:** Singleton configuration table (`workflow_settings`) with revision history (`workflow_settings_history`) and automatic `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migrations.

---

## Configuration & Environment Variables

Environment variables are loaded via `pydantic-settings` from `.env`:

| Variable | Default Value | Description |
|---|---|---|
| `DRONEWATCH_GCP_PROJECT_ID` | `dronewatch-project` | Google Cloud project ID for Vertex AI |
| `DRONEWATCH_GCP_LOCATION` | `global` | Vertex AI regional endpoint location |
| `DRONEWATCH_GEMINI_MODEL` | `gemini-3.6-flash` | Default Gemini model version for Tier 2 escalation |
| `DRONEWATCH_USE_VERTEX_AI` | `true` | Enable Vertex AI client initialization |
| `DRONEWATCH_ENABLE_TIER1_GEMMA` | `false` | Enable Tier 1 Gemma inference triage gate |
| `DRONEWATCH_TRIAGE_MODE` | `DECISION_FRAMEWORK` | Tier 1 mode (`DECISION_FRAMEWORK` or `KEYWORD_LEGACY`) |
| `DRONEWATCH_GEMMA_SERVICE_URL` | `""` | Internal Cloud Run URL for Tier 1 triage |
| `DRONEWATCH_GEMMA_MODEL_NAME` | `google/gemma-4-E2B-it` | Target model identifier served by vLLM |
| `DRONEWATCH_SUPPRESS_THRESHOLD` | `0.25` | Band 0 ceiling below which `P(threat)` is suppressed |
| `DRONEWATCH_GEMMA_TRIAGE_THRESHOLD` | `0.50` | Band 2 cutoff at/above which `P(threat)` escalates immediately |
| `DRONEWATCH_CORROBORATION_HITS` | `2` | Required Band 1 hits (`k`) within window (`n`) to escalate |
| `DRONEWATCH_CORROBORATION_WINDOW` | `3` | Non-blocking per-stream ring buffer window size (`n`) |
| `DRONEWATCH_ESCALATION_COOLDOWN_SECONDS` | `3.0` | Anti-snowball cooldown suppressing duplicate non-`CRITICAL` calls |
| `DRONEWATCH_GEMMA_TIMEOUT_SECONDS` | `2.0` | Maximum timeout before circuit breaker fails open to Gemini |
| `DRONEWATCH_GEMMA_TRIAGE_PROMPT` | `"detect campus security anomalies..."` | Policy criteria evaluated during Tier 1 triage |
| `DRONEWATCH_GEMMA_SCENE_DESCRIPTION_INTERVAL_SECONDS` | `10.0` | Cadence for routine surveillance HUD telemetry |
| `DRONEWATCH_GEMMA_SCENE_DESCRIPTION_PROMPT` | `"Briefly describe this drone surveillance..."` | Prompt for 10s HUD scene heartbeat |
| `DRONEWATCH_FRAME_SAMPLING_FPS` | `1.0` | Target frame evaluation rate (frames/sec) |
| `DRONEWATCH_MOTION_SENSITIVITY_THRESHOLD` | `15.0` | OpenCV pixel delta intensity threshold |
| `DRONEWATCH_MIN_MOTION_AREA` | `500` | Minimum pixel contour area to trigger Tier 1 evaluation |
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
INFO: Tier 1 Gemma vision triage [drone-alpha]: mode='DECISION_FRAMEWORK' | response='SAFE' | verdict=SAFE score=0.042 entropy=0.118 tags=['safe'] (latency=19.4ms)
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
> **Cold Start Handling:** When `dronewatch-gemma-triage` scales to zero (`min-instances=0`), an incoming request during container cold start will encounter a brief delay (~35s–45s). The backend's resilient **fail-open circuit breaker** catches the HTTP timeout, immediately escalates the frame to Gemini 3.6 Flash (`CIRCUIT_BREAKER_BYPASS`) without dropping surveillance, and logs a recovery notice once Gemma returns `200 OK`.

---

## Project Structure

```
dronewatch/
├── docs/
│   └── ARCHITECTURE.md               # v3.0 System 1 Decision Framework Architecture Specification
├── frontend/                         # React + Vite frontend application
│   ├── src/
│   │   ├── components/               # UI Components (StreamGrid, Header, AlertSidebar, AdminView)
│   │   └── App.jsx                   # Main React entry point
│   ├── package.json                  # Frontend dependencies
│   └── vite.config.js                # Vite dev server configuration
├── scripts/                          # Automated deployment scripts
│   ├── deploy_gcp.sh                 # Cloud Run Backend deployment script
│   └── deploy_gemma_triage.sh        # Parameterized Cloud Run GPU (RTX Pro 6000 / L4) vLLM script
├── src/dronewatch/                   # Core Python backend package
│   ├── db/                           # AlloyDB / local memory store implementations
│   ├── models/                       # Pydantic v2 schemas
│   │   ├── events.py                 # IncidentEvent, AnalysisResult & routing/dispatch contracts
│   │   ├── triage.py                 # TriageVerdict, TriageClassProbabilities & Routing/Dispatch enums
│   │   └── workflow_config.py        # WorkflowConfig (3-band + corroboration + cooldown schemas)
│   ├── services/
│   │   ├── analyzer.py               # Gemini vision analyzer service (dynamic model support)
│   │   ├── decision_engine.py        # Deterministic 3-band routing, O(1) corroboration & anti-snowball
│   │   ├── gemma_client.py           # Logprob-calibrated Tier 1 triage & Tier 2 deep inspection client
│   │   ├── motion_filter.py          # OpenCV motion pre-filtering service
│   │   └── stream_processor.py       # Ingestion engine with non-blocking corroboration & watermarks
│   ├── config.py                     # Application settings (pydantic-settings)
│   └── main.py                       # FastAPI REST API & WebSocket endpoints (v3.0.0)
├── tests/                            # Pytest test suite (72 tests)
│   ├── test_api.py                   # REST API and WebSocket tests
│   ├── test_analyzer.py              # Gemini analyzer tests (dynamic models)
│   ├── test_decision_engine.py       # Logprob calibration, 3-band routing, cooldown & watermark tests
│   ├── test_events_model.py          # Pydantic schema validation tests
│   ├── test_gemma_client.py          # Gemma client unit tests (OIDC, triage, circuit breaker)
│   ├── test_stream_processor_gemma.py # Stream processor tiered pipeline tests
│   └── test_workflow_config.py       # Workflow configuration API, AlloyDB & routing tests
├── pyproject.toml                    # Python project configuration (uv/ruff/pytest)
└── README.md                         # Project documentation
```
