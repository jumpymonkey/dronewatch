# DroneWatch — Real-Time Multi-Drone Surveillance & AI Analytics

## Overview
**DroneWatch** is an enterprise cloud-native web application designed for real-time security surveillance analytics and multi-drone flight oversight powered by **Google Gemini 3.1 Flash Live** and **Google Cloud Platform (GCP)**.

## Project Goal
The primary goal of DroneWatch is to solve operator cognitive overload for drone pilots and security personnel who must oversee multiple live drone feeds simultaneously. 

By bridging live RTSP video streams with Gemini's multimodal artificial intelligence, DroneWatch continuously analyzes aerial video feeds in real time, automatically logs timestamped analytical findings into **Google Cloud AlloyDB**, and delivers sub-second visual and auditory alerts to pilots whenever urgent critical security events (e.g., perimeter breaches, fires, unauthorized vehicles) are detected.

## Key Features
* **Live RTSP Stream Connection:** Ingest and render multiple low-latency drone video feeds in a unified Web UI dashboard.
* **Gemini-Powered Video Understanding:** Continuous visual understanding using **Google Gemini 3.1 Flash Live** (`BidiGenerateContent` over WebSockets) for real-time threat detection and automated severity classification.
* **Timestamped AlloyDB Persistence:** Structured storage of visual analytics and bounding boxes in Google Cloud AlloyDB for PostgreSQL with `pgvector` semantic search.
* **Real-Time Pilot Alerts:** Instant WebSocket push notifications with visual highlights and audible alarms for high-priority threats.
* **RTSP Test & Simulation Suite:** Built-in utility to stream local MP4 video files as live RTSP feeds for hardware-free testing and AI model validation.

## Documentation Links
* [Product Requirement Document (PRD)](dronewatch.md)
* [GCP Native Cloud Architecture Blueprint](dronewatch_architecture.md)
