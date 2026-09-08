# Cloud Run v2 Service for DroneWatch Backend & UI
resource "google_cloud_run_v2_service" "backend" {
  name     = "dronewatch-service-${var.environment}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.dronewatch_sa.email

    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc_network.name
        subnetwork = google_compute_subnetwork.subnet.name
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

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
        name  = "DB_USER"
        value = "postgres"
      }
      env {
        name  = "DB_PASSWORD"
        value = var.alloydb_password
      }
      env {
        name  = "DB_NAME"
        value = "postgres"
      }
      env {
        name  = "DB_SSL"
        value = "true"
      }
    }
  }
}


