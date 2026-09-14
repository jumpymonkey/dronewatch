# Multi-stage production Dockerfile for DroneWatch on Cloud Run
FROM ghcr.io/astral-sh/uv:0.5.10-python3.12-bookworm-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ruff.toml README.md ./
COPY src/ ./src/

# Install python dependencies into virtual environment
RUN uv sync --frozen --no-dev || uv sync --no-dev

FROM python:3.12-slim-bookworm AS runner

WORKDIR /app

# Install runtime libs for OpenCV and GStreamer
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

CMD ["uvicorn", "dronewatch.main:app", "--host", "0.0.0.0", "--port", "8080"]
