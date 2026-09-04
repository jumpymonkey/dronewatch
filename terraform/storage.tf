# GCS Bucket for Storing Video Clip Highlights & Frame Artifacts
resource "google_storage_bucket" "drone_clips" {
  name                     = "dronewatch-clips-${var.project_id}-${var.environment}"
  location                 = var.region
  force_destroy            = true
  public_access_prevention = "enforced"

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  uniform_bucket_level_access = true
}
