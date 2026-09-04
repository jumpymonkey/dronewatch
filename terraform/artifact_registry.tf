# Artifact Registry Docker Repository
resource "google_artifact_registry_repository" "dronewatch_repo" {
  location      = var.region
  repository_id = "dronewatch-repo-${var.environment}"
  description   = "Docker repository for DroneWatch platform container images"
  format        = "DOCKER"
}
