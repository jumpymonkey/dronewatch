# Service Account for DroneWatch Cloud Run Backend Service
resource "google_service_account" "dronewatch_sa" {
  account_id   = "dronewatch-runner-${var.environment}"
  display_name = "DroneWatch Cloud Run Runner Service Account"
}

# Grant Vertex AI User Role for Gemini Live Processing
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.dronewatch_sa.email}"
}

# Grant Cloud Pub/Sub Publisher Role for Real-Time Alerts
resource "google_project_iam_member" "pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.dronewatch_sa.email}"
}

# Grant Storage Object Admin Role for Video Highlights & Frames
resource "google_project_iam_member" "storage_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.dronewatch_sa.email}"
}

# Grant AlloyDB Client Role for Database Access
resource "google_project_iam_member" "alloydb_client" {
  project = var.project_id
  role    = "roles/alloydb.client"
  member  = "serviceAccount:${google_service_account.dronewatch_sa.email}"
}
