#!/usr/bin/env bash
set -euo pipefail

# GCP Deployment Script for DroneWatch Service on Cloud Run
PROJECT_ID="${GCP_PROJECT_ID:-jal-dronewatch}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="dronewatch-backend"
REPO_NAME="dronewatch-repo"
IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"

echo "=== DroneWatch GCP Cloud Run Deployment ==="
echo "Project ID: ${PROJECT_ID}"
echo "Region:     ${REGION}"
echo "Image:      ${IMAGE_NAME}"

# 1. Enable required GCP APIs
echo "--> Enabling GCP APIs..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    aiplatform.googleapis.com \
    alloydb.googleapis.com \
    pubsub.googleapis.com \
    storage.googleapis.com \
    vpcaccess.googleapis.com \
    --project="${PROJECT_ID}"

# 2. Create Artifact Registry Docker repository if not exists
echo "--> Verifying Artifact Registry repository..."
if ! gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud artifacts repositories create "${REPO_NAME}" \
        --repository-format=docker \
        --location="${REGION}" \
        --description="DroneWatch Docker container repository" \
        --project="${PROJECT_ID}"
fi

# 3. Build container image using Cloud Build
echo "--> Building container image with Cloud Build..."
gcloud builds submit --tag "${IMAGE_NAME}" --project="${PROJECT_ID}" .

# 4. Deploy service to Cloud Run with Direct VPC egress to AlloyDB
echo "--> Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
    --image="${IMAGE_NAME}" \
    --platform=managed \
    --region="${REGION}" \
    --allow-unauthenticated \
    --network=dronewatch-vpc-prod \
    --subnet=dronewatch-subnet-us-central1-prod \
    --vpc-egress=all-traffic \
    --set-env-vars="DRONEWATCH_GCP_PROJECT_ID=${PROJECT_ID},DRONEWATCH_GCP_LOCATION=${REGION},DRONEWATCH_GEMINI_MODEL=gemini-3.6-flash,DRONEWATCH_ENVIRONMENT=production,DRONEWATCH_ALLOYDB_HOST=10.208.115.2,DRONEWATCH_ALLOYDB_PORT=5432,DRONEWATCH_ALLOYDB_DB=postgres,DRONEWATCH_ALLOYDB_USER=postgres,DRONEWATCH_ALLOYDB_PASSWORD=dronewatch_pass_2026" \
    --min-instances=1 \
    --cpu=2 \
    --memory=4Gi \
    --project="${PROJECT_ID}"

echo "=== Deployment Completed Successfully ==="
gcloud run services describe "${SERVICE_NAME}" --platform=managed --region="${REGION}" --project="${PROJECT_ID}" --format="value(status.url)"
