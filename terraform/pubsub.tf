# Cloud Pub/Sub Topic for Urgent Threat Fan-Out
resource "google_pubsub_topic" "drone_alerts" {
  name = "dronewatch-alerts-topic-${var.environment}"
}

resource "google_pubsub_subscription" "alerts_push_sub" {
  name  = "dronewatch-alerts-sub-${var.environment}"
  topic = google_pubsub_topic.drone_alerts.name

  ack_deadline_seconds = 20

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.backend.uri}/api/v1/pubsub/push"
  }
}
