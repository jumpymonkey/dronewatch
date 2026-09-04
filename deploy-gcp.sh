#!/usr/bin/env bash
set -e

PROJECT_ID=${1:-"jal-dronewatch"}
REGION=${2:-"us-central1"}
ENV=${3:-"prod"}

echo "=========================================================="
echo "   DroneWatch Platform - GCP Production Deployment"
echo "   Project ID:  ${PROJECT_ID}"
echo "   Region:      ${REGION}"
echo "   Environment: ${ENV}"
echo "=========================================================="

# Export active gcloud access token for Terraform
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)

# Fetch project number for IAM permissions
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
echo "Project Number: ${PROJECT_NUMBER}"

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
    logging.googleapis.com \
    --project="${PROJECT_ID}"

# Ensure Cloud Build & Compute service accounts have Storage Admin, Artifact Registry Writer & Logging permissions
echo "Configuring IAM roles for Cloud Build & Compute service accounts..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/storage.admin" --condition=None > /dev/null 2>&1 || true

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/artifactregistry.writer" --condition=None > /dev/null 2>&1 || true

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/logging.logWriter" --condition=None > /dev/null 2>&1 || true

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
    --role="roles/storage.admin" --condition=None > /dev/null 2>&1 || true

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
    --role="roles/artifactregistry.writer" --condition=None > /dev/null 2>&1 || true

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
    --role="roles/logging.logWriter" --condition=None > /dev/null 2>&1 || true

IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/dronewatch-repo-${ENV}/dronewatch-backend:latest"

# 2. Provision Artifact Registry repository first
echo "[2/5] Initializing Artifact Registry & Core Infrastructure..."
cd terraform
terraform init
terraform apply -auto-approve \
    -target=google_artifact_registry_repository.dronewatch_repo \
    -var="project_id=${PROJECT_ID}" \
    -var="region=${REGION}" \
    -var="environment=${ENV}"
cd ..

# 3. Build & Push Container via Cloud Build
echo "[3/5] Building & Pushing Unified Production Container Image (${IMAGE_TAG})...."
gcloud builds submit . \
    --config=cloudbuild.yaml \
    --substitutions=_IMAGE_TAG="${IMAGE_TAG}" \
    --project="${PROJECT_ID}"

# 4. Provision full GCP Cloud Infrastructure with Terraform (including Cloud Run)
echo "[4/5] Deploying Cloud Run & Full GCP Infrastructure via Terraform..."
cd terraform
terraform apply -auto-approve \
    -var="project_id=${PROJECT_ID}" \
    -var="region=${REGION}" \
    -var="environment=${ENV}"
cd ..

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
