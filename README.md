# DroneWatch 🛰️

**AI-Powered Multi-Drone Campus Surveillance & Real-Time Threat Detection System**

DroneWatch provides real-time AI-powered threat detection, multi-camera RTSP ingestion, motion-filtered video stream analysis, and instant dispatch alerting across campus surveillance networks.

---

## Architecture Overview

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

## Development & Testing

### Prerequisites
- Python 3.12+
- `uv` package manager

### Installation & Execution

```bash
# Sync virtual environment and dependencies
uv sync

# Run static analysis and linting
uv run ruff check .
uv run ruff format --check .

# Run test suite
uv run pytest

# Launch FastAPI backend
uv run uvicorn dronewatch.main:app --host 0.0.0.0 --port 8000 --reload

# Launch Vite frontend dev server (in frontend/)
npm run dev -- --host 0.0.0.0 --port 3000
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
