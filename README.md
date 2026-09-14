# DroneWatch

AI-Powered Multi-Drone Campus Surveillance & Real-Time Threat Detection System.

## Architecture
- **Inference Model:** Gemini 3.6 Flash (`gemini-3.6-flash`) via Google GenAI / Vertex AI SDK
- **Database:** AlloyDB for PostgreSQL with `pgvector` extension
- **Backend:** FastAPI + WebSockets + Pydantic v2
- **Pre-Filtering:** Motion pre-filter using OpenCV frame differencing
- **Deployment:** Cloud Run, Artifact Registry, Google Cloud Storage

## Quickstart
```bash
# Sync dependencies
uv sync

# Run tests
uv run pytest

# Run FastAPI backend server
uv run uvicorn dronewatch.main:app --reload
```
