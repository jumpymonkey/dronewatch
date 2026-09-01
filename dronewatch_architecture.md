# DroneWatch — Google Cloud Native Architecture & Deployment Blueprint

**Document Title:** DroneWatch GCP Cloud Native Deployment Architecture  
**Target File:** `dronewatch_architecture.md`  
**Date:** September 1, 2026  
**Status:** Architecture Design Document (ADD)  
**Cloud Provider:** Google Cloud Platform (100% GCP Native Services)  

---

## 1. Architecture Overview & Principles

DroneWatch is designed as an enterprise-grade, cloud-native SaaS platform deployed entirely on **Google Cloud Platform (GCP)**. The system processes high-throughput live RTSP feeds from drone fleets, executes real-time AI video understanding using **Vertex AI (Gemini 3.1 Flash Live)**, persists timestamped analytical events to **AlloyDB for PostgreSQL**, and pushes instant sub-second critical alerts to drone pilot web applications.

```
                                      +-------------------------------------------------+
                                      |          FIELD DRONES & TEST SIMULATOR          |
                                      +-------------------------------------------------+
                                           |                                |
                                           v (Live RTSP)                    v (GCS MP4 Test Videos)
                                      +-------------------------------------------------+
                                      |             GCP EDGE / INGESTION                |
                                      |           Cloud Armor + Cloud Load Balancer      |
                                      +-------------------------------------------------+
                                                               |
                                                               v
                                      +-------------------------------------------------+
                                      |           COMPUTE & PROCESSING LAYER            |
                                      |          Cloud Run / GKE Autopilot              |
                                      |     (FFmpeg Decoders & Stream Transcoders)      |
                                      +-------------------------------------------------+
                                           /                   |                   \
            (Stream Frames)               /                    | (WebRTC / HLS)     \ (Publish Alerts)
                                         v                     v                     v
+-------------------------------------------------+   +------------------+   +----------------------------------+
|               VERTEX AI ENGINE                  |   |  MEDIA & CDN     |   |          MESSAGING LAYER         |
|        Gemini 3.1 Flash Live API                |   |    Cloud CDN     |   |         Google Cloud Pub/Sub     |
|   (BidiGenerateContent over WebSockets)         |   +------------------+   +----------------------------------+
+-------------------------------------------------+            |                              |
                        |                                      v                              v
                        | (Structured Detections)     +------------------+   +----------------------------------+
                        v                             |  FRONTEND UI     |   |        REAL-TIME DISPATCH        |
+-------------------------------------------------+   | Pilot Web App    |   | Cloud Run (WebSocket Gateway)    |
|               DATABASE & STORAGE                |   | (Cloud Storage / |   +----------------------------------+
|   AlloyDB for PostgreSQL (with pgvector)        |   |   Cloud CDN)     |                    |
|   + Google Cloud Storage (GCS Media Archive)    |   +------------------+                    v
+-------------------------------------------------+                            +----------------------------+
                                                                               |   Pilot Browser / Web UI   |
                                                                               +----------------------------+
```

---

## 2. GCP Native Service Mapping

| Architectural Layer | DroneWatch Function | Recommended GCP Native Service | Rationale / Capabilities |
| :--- | :--- | :--- | :--- |
| **Ingestion Gateway** | RTSP Feed Termination & Stream Management | **Cloud Run** / **GKE Autopilot** | Cloud Run supports continuous CPU allocation, WebSockets/gRPC, containerized FFmpeg, and auto-scaling per active stream count. |
| **Video Stream Transcoding** | RTSP-to-WebRTC / LL-HLS Bridge for Browser | **Cloud Run** + **Cloud CDN** | Transcodes raw RTSP into low-latency WebRTC/HLS feeds for browser rendering with global CDN caching. |
| **AI Video Understanding** | Real-Time Video Analysis & Anomaly Detection | **Vertex AI (Gemini 3.1 Flash Live)** | Native Vertex AI endpoint using `BidiGenerateContent` over WebSockets for sub-second multimodal video reasoning. |
| **Relational & Vector DB** | Timestamped Log Storage & Vector Search | **AlloyDB for PostgreSQL** | Up to 100x faster analytical queries than standard Postgres, built-in `pgvector` for semantic search, and enterprise HA/DR. |
| **Media Archiving** | Snapshot & Full Video Clip Archive | **Google Cloud Storage (GCS)** | Regional/Multi-regional buckets with Lifecycle Management for storing `CRITICAL` alert frames and historical flight videos. |
| **Event Bus & Decoupling** | Asynchronous Alert & Pipeline Messaging | **Cloud Pub/Sub** | High-throughput, low-latency event broker decoupling Gemini detection events from database writes and UI pushes. |
| **Real-Time UI Push** | WebSocket Dispatcher for Pilot Alerts | **Cloud Run (WebSocket Service)** | Maintains persistent WebSockets to pilot browser clients, broadcasting `CRITICAL` threat banners instantly. |
| **Test Simulation Suite** | Local/Remote MP4-to-RTSP Streamer | **Cloud Run Jobs** + **GCS Bucket** | Cloud Run Jobs execute containerized FFmpeg processes that loop test MP4s stored in GCS into virtual RTSP streams. |
| **Edge Security & WAF** | DDoS Protection & TLS Termination | **Cloud Armor** + **Cloud Load Balancing** | Enterprise WAF, rate-limiting, SSL termination, and protection against OWASP Top 10 vulnerabilities. |
| **Authentication & Access** | Pilot Identity & Zero-Trust IAM | **Identity-Aware Proxy (IAP)** + **Cloud IAM** | Context-aware access control enforcing Google SSO and fine-grained role-based access control (RBAC). |
| **Secrets Management** | DB Credentials, API Keys, RTSP Passwords | **Secret Manager** | Centralized, versioned secret management integrated seamlessly with Cloud Run and Vertex AI. |
| **Observability & Logging** | System Health, Stream Drops, AI Latency | **Cloud Logging** & **Cloud Monitoring** | Pre-built dashboards, alert policies for stream dropouts, Gemini rate-limiting, and DB CPU utilization. |

---

## 3. Detailed Architectural Components

### 3.1 RTSP Stream Ingestion & Processing (Cloud Run / GKE Autopilot)
* **Deployment Pattern:** Containerized microservice running **FFmpeg** and **MediaMTX** deployed on **Cloud Run** (with Always-on CPU allocation) or **GKE Autopilot**.
* **Stream Handling:**
  1. Microservice accepts incoming RTSP connections (`rtsp://drone-ip:554/live`).
  2. Spawns two processing pipes per stream:
     * **Pipe A (Web Player):** Transcodes video into Low-Latency HLS / WebRTC pushed to Cloud CDN for pilot monitoring.
     * **Pipe B (AI Engine):** Extracts JPEG frames at 1–2 FPS and pipes them via WebSockets directly into Vertex AI.

### 3.2 AI Video Understanding Pipeline (Vertex AI Gemini 3.1 Flash Live)
* **Connection Protocol:** Persistent WebSocket connection established between Cloud Run workers and **Vertex AI Multimodal Live API (`BidiGenerateContent`)**.
* **Payload Structure:** Continuous stream of JPEG frame chunks paired with a system instruction prompt demanding strict JSON responses:
  ```json
  {
    "stream_id": "drone-north-04",
    "timestamp": "2026-09-01T21:10:00.123456Z",
    "severity": "CRITICAL",
    "category": "Intrusion",
    "summary": "Unauthorized person climbing North Perimeter Fence",
    "bounding_box": {"ymin": 120, "xmin": 450, "ymax": 380, "xmax": 610}
  }
  ```
* **Error Resilience:** If Gemini API rate limits occur, Cloud Run automatically falls back from 2 FPS to 0.5 FPS sampling without dropping the RTSP video stream.

### 3.3 Relational & Vector Persistence (AlloyDB for PostgreSQL)
* **Primary Database:** **Google Cloud AlloyDB Primary Instance** with read replicas in a high-availability private VPC configuration.
* **Database Driver & Pooling:** Connections managed via Cloud SQL Auth Proxy / AlloyDB Language Connectors using PgBouncer pooling.
* **Vector Embeddings:** Uses `pgvector` to store 768-dimensional embeddings of detection summaries, enabling security analysts to query historical logs using natural language (e.g., *"Find all instances of red trucks near the east gate"*).

### 3.4 Decoupled Messaging & Real-Time Alerting (Pub/Sub + Cloud Run)
1. When Vertex AI identifies a `CRITICAL` alert, the ingest worker publishes a JSON payload to a **Pub/Sub Topic** (`dronewatch-urgent-alerts`).
2. Two independent Cloud Pub/Sub subscriptions process the message asynchronously:
   * **Subscription 1 (AlloyDB Writer):** Cloud Run worker batch-inserts records into AlloyDB.
   * **Subscription 2 (WebSocket Push Gateway):** Cloud Run WebSocket service pushes an immediate notification frame to connected pilot browsers.

### 3.5 RTSP Test & Simulation Engine (Cloud Run Jobs + GCS)
* **Video Archive:** Test footage (e.g., `DJI_0104.MP4`, `S1001976.MP4`) stored in a dedicated GCS bucket (`gs://dronewatch-simulation-videos/`).
* **Execution:** Users launch a simulation test via the UI. The backend triggers a **Cloud Run Job** that streams the GCS video file on a continuous loop to a temporary RTSP endpoint.
* **Integration:** The main application treats this simulated RTSP endpoint identically to a physical drone stream.

---

## 4. Network, Security & IAM Infrastructure

```
                                    +-----------------------------------------+
                                    |              INTERNET                   |
                                    +-----------------------------------------+
                                                         |
                                                         v
                                    +-----------------------------------------+
                                    |   Cloud Armor (WAF / DDoS Protection)   |
                                    +-----------------------------------------+
                                                         |
                                                         v
                                    +-----------------------------------------+
                                    |  External HTTPS / WebSockets Load Balancer |
                                    +-----------------------------------------+
                                                         |
                                                         v
                               +---------------------------------------------------+
                               |              PROJECT VPC NETWORK                  |
                               |                                                   |
                               |  +---------------------------------------------+  |
                               |  |  Private Service Connect / Serverless VPC  |  |
                               |  +---------------------------------------------+  |
                               |          /               |                \       |
                               |         v                v                 v      |
                               |  +--------------+  +-----------+  +------------+  |
                               |  |  Cloud Run   |  |  AlloyDB  |  | Vertex AI  |  |
                               |  |  Services    |  | Cluster   |  | Endpoints  |  |
                               |  +--------------+  +-----------+  +------------+  |
                               +---------------------------------------------------+
```

### 4.1 Security & Access Controls
* **Network Isolation:** All database traffic, Pub/Sub communication, and Vertex AI API traffic route over a **Serverless VPC Access Connector** and **Private Service Connect (PSC)** without exposing public IP addresses.
* **Zero-Trust Authentication:**
  * User access governed by **Identity-Aware Proxy (IAP)** enforcing Google SSO and Multi-Factor Authentication (MFA).
  * Cloud Run microservices authenticate to AlloyDB and Vertex AI using **Workload Identity** and Service Accounts (no hardcoded passwords or long-lived API tokens).
* **Secrets Management:** Sensitive keys and database passwords managed centrally in **Google Cloud Secret Manager** with automatic rotation.

---

## 5. Operations, Monitoring & Scalability

### 5.1 Monitoring Dashboards (Cloud Monitoring)
* **RTSP Stream Health Metric:** Active streams, reconnect attempts, dropped frame count.
* **Gemini Inference Latency Metric:** Sub-second latency tracking for `BidiGenerateContent` WebSocket responses.
* **AlloyDB Performance Metric:** CPU utilization, connection pool saturation, write transaction latency.

### 5.2 Scalability Targets
* **Horizontal Auto-Scaling:** Cloud Run automatically scales up instances as new drone RTSP feeds are added, maintaining up to 50 active streams per cluster.
* **Database High Availability:** AlloyDB configured with multi-zone availability, automated cross-region back-ups, and read pools to support heavy analytical queries without impacting live ingestion.

---

## 6. Infrastructure-as-Code (Terraform) Component Blueprint

Below is the conceptual Terraform module structure for provisioning the GCP native stack:

```hcl
# Main Terraform Blueprint for DroneWatch GCP Infrastructure

module "vpc_network" {
  source       = "terraform-google-modules/network/google"
  network_name = "dronewatch-vpc"
  subnets      = [{ name = "dronewatch-subnet", subnet_ip = "10.0.0.0/20", subnet_region = "us-central1" }]
}

module "alloydb" {
  source        = "terraform-google-modules/alloydb/google"
  cluster_id    = "dronewatch-alloydb-cluster"
  primary_spec  = { instance_id = "dronewatch-primary", cpu_count = 4 }
  network_id    = module.vpc_network.network_id
}

resource "google_cloud_run_v2_service" "ingestion_worker" {
  name     = "dronewatch-rtsp-worker"
  location = "us-central1"
  template {
    containers {
      image = "us-central1-docker.pkg.dev/dronewatch-proj/repo/worker:latest"
      resources { limits = { cpu = "2", memory = "4Gi" } }
    }
  }
}

resource "google_pubsub_topic" "urgent_alerts" {
  name = "dronewatch-urgent-alerts"
}
```

---

## 7. Deliverables Summary

1. `dronewatch_architecture.md` — Full GCP Native Cloud Architecture & Blueprint (This document).
2. `dronewatch.md` — Product Requirement Document (PRD).
