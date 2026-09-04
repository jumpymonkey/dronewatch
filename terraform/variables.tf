variable "project_id" {
  type        = string
  description = "GCP Project ID"
  default     = "dronewatch-prod"
}

variable "region" {
  type        = string
  description = "GCP Deployment Region"
  default     = "us-central1"
}

variable "environment" {
  type        = string
  description = "Deployment Environment (dev, staging, prod)"
  default     = "prod"
}

variable "alloydb_password" {
  type        = string
  description = "AlloyDB Cluster Superuser Password"
  sensitive   = true
  default     = "DroneWatchSuperSecure2026!"
}
