#!/usr/bin/env bash
set -euo pipefail

# GCP Deployment Script for DroneWatch Tier 1 Gemma Triage Service on Cloud Run (GPU)
# Uses Google prebuilt vLLM container for Gemma 4 (google/gemma-4-E2B-it)
PROJECT_ID="${GCP_PROJECT_ID:-jal-dronewatch}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="dronewatch-gemma-triage"
PREBUILT_IMAGE="us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:gemma4"
MODEL_NAME="google/gemma-4-E2B-it"
BACKEND_SA="${BACKEND_SERVICE_ACCOUNT:-543569011042-compute@developer.gserviceaccount.com}"

echo "=== DroneWatch Tier 1 Gemma Triage Cloud Run Deployment ==="
echo "Project ID: ${PROJECT_ID}"
echo "Region:     ${REGION}"
echo "Service:    ${SERVICE_NAME}"
echo "Image:      ${PREBUILT_IMAGE}"
echo "Model:      ${MODEL_NAME}"
echo "Backend SA: ${BACKEND_SA}"

# 1. Enable required GCP APIs
echo "--> Enabling GCP APIs..."
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    --project="${PROJECT_ID}"

# 2. Deploy service to Cloud Run with NVIDIA RTX Pro 6000 GPU
MODELS_BUCKET="${GCS_MODELS_BUCKET:-jal-dronewatch-models}"
LOCAL_MODEL_PATH="/models/gemma-4-E2B-it"

echo "--> Deploying ${SERVICE_NAME} with NVIDIA RTX Pro 6000 GPU and GCS Volume Mount (${MODELS_BUCKET})..."
CONTAINER_ARGS=(
  "serve"
  "${LOCAL_MODEL_PATH}"
  "--served-model-name=${MODEL_NAME}"
  "--enable-chunked-prefill"
  "--enable-prefix-caching"
  "--generation-config=auto"
  "--enable-auto-tool-choice"
  "--tool-call-parser=gemma4"
  "--reasoning-parser=gemma4"
  "--dtype=bfloat16"
  "--max-num-seqs=64"
  "--gpu-memory-utilization=0.95"
  "--tensor-parallel-size=1"
  "--port=8080"
  "--host=0.0.0.0"
)

ARGS_CSV=$(IFS=','; echo "${CONTAINER_ARGS[*]}")

CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
gcloud beta run deploy "${SERVICE_NAME}" \
    --image="${PREBUILT_IMAGE}" \
    --platform=managed \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
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
    --args="${ARGS_CSV}"

# 3. Grant Ingestion Backend permission to invoke Tier 1 service
if [[ -n "${BACKEND_SA}" ]]; then
    echo "--> Binding roles/run.invoker to ${BACKEND_SA}..."
    CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
    gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
        --region="${REGION}" \
        --member="serviceAccount:${BACKEND_SA}" \
        --role="roles/run.invoker" \
        --project="${PROJECT_ID}"
fi

echo "=== Tier 1 Gemma Triage Deployed Successfully ==="
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
gcloud run services describe "${SERVICE_NAME}" --platform=managed --region="${REGION}" --project="${PROJECT_ID}" --format="value(status.url)"
