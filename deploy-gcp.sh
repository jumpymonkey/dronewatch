#!/usr/bin/env bash
set -e

PROJECT_ID=${1:-"dronewatch-prod"}
REGION=${2:-"us-central1"}
ENV=${3:-"prod"}

echo "=========================================================="
echo "   DroneWatch Platform - GCP Production Deployment"
echo "   Project ID:  ${PROJECT_ID}"
echo "   Region:      ${REGION}"
echo "   Environment: ${ENV}"
echo "=========================================================="

# 1. Enable required GCP Service APIs
echo "[1/5] Enabling Google Cloud Infrastructure APIs..."
gcloud services enable \
    run.googleapis.com \
    alloydb.googleapis.com \
    pubsub.googleapis.com \
    storage.googleapis.com \
    aiplatform.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    compute.googleapis.com \
    servicenetworking.googleapis.com \
    --project="${PROJECT_ID}"

# 2. Provision Infrastructure via Terraform
echo "[2/5] Provisioning GCP Cloud Resources via Terraform..."
cd terraform
terraform init
terraform apply -auto-approve \
    -var="project_id=${PROJECT_ID}" \
    -var="region=${REGION}" \
    -var="environment=${ENV}"

IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/dronewatch-repo-${ENV}/dronewatch-backend:latest"
cd ..

# 3. Configure Docker Authentication & Build via Cloud Build
echo "[3/5] Building & Pushing Unified Production Container Image (${IMAGE_TAG})..."
gcloud builds submit . \
    --tag="${IMAGE_TAG}" \
    --project="${PROJECT_ID}"

# 4. Deploy Container to Cloud Run
echo "[4/5] Updating Cloud Run Service with New Build Image..."
gcloud run deploy "dronewatch-service-${ENV}" \
    --image="${IMAGE_TAG}" \
    --region="${REGION}" \
    --platform=managed \
    --project="${PROJECT_ID}"

# 5. Fetch Production URL
SERVICE_URL=$(gcloud run services describe "dronewatch-service-${ENV}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)')

echo "=========================================================="
echo "   🎉 GCP Production Deployment Complete!"
echo "   ------------------------------------------------------"
echo "   DroneWatch Platform URL: ${SERVICE_URL}"
echo "   AlloyDB Vector DB:       Provisioned with pgvector"
echo "   Vision AI Model:         Vertex AI Gemini 3.1 Flash Live"
echo "   Alert Fan-Out:           Cloud Pub/Sub topic"
echo "=========================================================="
