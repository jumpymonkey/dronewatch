#!/usr/bin/env bash
set -euo pipefail

# GCP Deployment Script for DroneWatch Service on Cloud Run
PROJECT_ID="${GCP_PROJECT_ID:-jal-dronewatch}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="dronewatch-backend"
REPO_NAME="dronewatch-repo"
IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"
GEMMA_SERVICE_NAME="dronewatch-gemma-triage"

echo "=== DroneWatch GCP Cloud Run Backend Deployment ==="
echo "Project ID: ${PROJECT_ID}"
echo "Region:     ${REGION}"
echo "Image:      ${IMAGE_NAME}"

# 1. Enable required GCP APIs
echo "--> Enabling GCP APIs..."
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    aiplatform.googleapis.com \
    alloydb.googleapis.com \
    storage.googleapis.com \
    vpcaccess.googleapis.com \
    --project="${PROJECT_ID}"

# 2. Retrieve Tier 1 Gemma Triage Service URL if available
GEMMA_SERVICE_URL=$(CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
    gcloud run services describe "${GEMMA_SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --format="value(status.url)" 2>/dev/null || echo "")

ENABLE_TIER1="false"
if [[ -n "${GEMMA_SERVICE_URL}" ]]; then
    ENABLE_TIER1="true"
    echo "--> Detected Tier 1 Gemma service at: ${GEMMA_SERVICE_URL}"
else
    echo "--> Tier 1 Gemma service not detected. Deploying with Tier 1 disabled."
fi

# AlloyDB Configuration
ALLOYDB_HOST="${ALLOYDB_HOST:-10.208.115.2}"
ALLOYDB_PORT="${ALLOYDB_PORT:-5432}"
ALLOYDB_DATABASE="${ALLOYDB_DATABASE:-postgres}"
ALLOYDB_USER="${ALLOYDB_USER:-postgres}"
ALLOYDB_PASSWORD="${ALLOYDB_PASSWORD:-dronewatch_pass_2026}"

# 3. Create Artifact Registry Docker repository if not exists
echo "--> Verifying Artifact Registry repository..."
if ! CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
    gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
    gcloud artifacts repositories create "${REPO_NAME}" \
        --repository-format=docker \
        --location="${REGION}" \
        --description="DroneWatch Docker container repository" \
        --project="${PROJECT_ID}"
fi

# 4. Compile React frontend production bundle
echo "--> Compiling React frontend SPA bundle..."
(cd frontend && npm run build)

# 5. Build container image using Cloud Build
echo "--> Building container image with Cloud Build..."
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
gcloud builds submit --tag "${IMAGE_NAME}" --project="${PROJECT_ID}" .

# 6. Deploy service to Cloud Run with Direct VPC egress to AlloyDB
echo "--> Deploying to Cloud Run..."
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
gcloud run deploy "${SERVICE_NAME}" \
    --image="${IMAGE_NAME}" \
    --platform=managed \
    --region="${REGION}" \
    --allow-unauthenticated \
    --network=dronewatch-vpc-prod \
    --subnet=dronewatch-subnet-us-central1-prod \
    --vpc-egress=private-ranges-only \
    --set-env-vars="DRONEWATCH_GCP_PROJECT_ID=${PROJECT_ID},GCP_PROJECT_ID=${PROJECT_ID},DRONEWATCH_GCP_LOCATION=global,DRONEWATCH_GEMINI_MODEL=gemini-3.6-flash,DRONEWATCH_ENVIRONMENT=production,DRONEWATCH_GCS_BUCKET_VIDEOS=jal-dronewatch-videos,DRONEWATCH_GCS_BUCKET_SNAPSHOTS=jal-dronewatch-snapshots,DRONEWATCH_ENABLE_TIER1_GEMMA=${ENABLE_TIER1},DRONEWATCH_GEMMA_SERVICE_URL=${GEMMA_SERVICE_URL},DRONEWATCH_GEMMA_MODEL_NAME=google/gemma-4-E2B-it,DRONEWATCH_ALLOYDB_HOST=${ALLOYDB_HOST},DRONEWATCH_ALLOYDB_PORT=${ALLOYDB_PORT},DRONEWATCH_ALLOYDB_DATABASE=${ALLOYDB_DATABASE},DRONEWATCH_ALLOYDB_USER=${ALLOYDB_USER},DRONEWATCH_ALLOYDB_PASSWORD=${ALLOYDB_PASSWORD}" \
    --min-instances=1 \
    --cpu=2 \
    --memory=8Gi \
    --project="${PROJECT_ID}"

echo "=== Deployment Completed Successfully ==="
CLOUDSDK_METRICS_ENVIRONMENT="${CLOUDSDK_METRICS_ENVIRONMENT:+$CLOUDSDK_METRICS_ENVIRONMENT }datacloud.antigravity" \
gcloud run services describe "${SERVICE_NAME}" --platform=managed --region="${REGION}" --project="${PROJECT_ID}" --format="value(status.url)"
