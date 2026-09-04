# AlloyDB Cluster for High-Performance pgvector Search
resource "google_alloydb_cluster" "dronewatch_cluster" {
  cluster_id = "dronewatch-alloydb-${var.environment}"
  location   = var.region
  network    = google_compute_network.vpc_network.id

  initial_user {
    password = var.alloydb_password
  }

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

resource "google_alloydb_instance" "dronewatch_primary" {
  cluster       = google_alloydb_cluster.dronewatch_cluster.name
  instance_id   = "dronewatch-primary-instance"
  instance_type = "PRIMARY"

  machine_config {
    cpu_count = 4
  }
}
