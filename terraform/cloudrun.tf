# Cloud Run v2 Service for DroneWatch Backend & UI
resource "google_cloud_run_v2_service" "backend" {
  name     = "dronewatch-service-${var.environment}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.dronewatch_sa.email

    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.dronewatch_repo.repository_id}/dronewatch-backend:latest"

      resources {
        limits = {
          cpu    = "2000m"
          memory = "2Gi"
        }
      }

      env {
        name  = "NODE_ENV"
        value = "production"
      }
      env {
        name  = "PORT"
        value = "8080"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "PUBSUB_TOPIC"
        value = google_pubsub_topic.drone_alerts.name
      }
      env {
        name  = "GCS_BUCKET_NAME"
        value = google_storage_bucket.drone_clips.name
      }
      env {
        name  = "DB_HOST"
        value = google_alloydb_instance.dronewatch_primary.ip_address
      }
      env {
        name  = "DB_NAME"
        value = "dronewatch"
      }
    }
  }
}

# Allow Public Unauthenticated Access to Cloud Run Service
resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  project  = google_cloud_run_v2_service.backend.project
  location = google_cloud_run_v2_service.backend.location
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
