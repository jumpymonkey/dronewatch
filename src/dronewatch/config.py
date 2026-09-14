"""Configuration settings for DroneWatch application using Pydantic Settings."""

import os

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings

# Disable mTLS client cert provider helper which causes status code -11 errors on Linux workstations
os.environ["CLOUDSDK_CONTEXT_AWARE_USE_CLIENT_CERTIFICATE"] = "false"
os.environ["GOOGLE_API_CERTIFICATE_CONFIG"] = ""
os.environ["OPENCV_FFMPEG_READ_ATTEMPTS"] = "20000"


class Settings(BaseSettings):
    """Application configuration settings."""

    model_config = ConfigDict(
        env_prefix="DRONEWATCH_",
        extra="forbid",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Application settings
    app_name: str = Field(default="DroneWatch")
    environment: str = Field(default="development")
    debug: bool = Field(default=True)

    # Google Cloud Platform Settings
    gcp_project_id: str = Field(
        default="your-gcp-project-id", description="GCP Project ID for Vertex AI / GenAI"
    )
    gcp_location: str = Field(default="us-central1", description="GCP Region")
    use_vertex_ai: bool = Field(default=True)
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model version for video analysis",
    )

    # Storage & AlloyDB Settings
    gcs_bucket_videos: str = Field(
        default="your-dronewatch-videos-bucket", description="GCS Bucket for video streams"
    )
    gcs_bucket_snapshots: str = Field(
        default="your-dronewatch-snapshots-bucket", description="GCS Bucket for alert snapshots"
    )
    alloydb_host: str | None = Field(default=None, description="AlloyDB PostgreSQL IP/Host")
    alloydb_port: int = Field(default=5432, description="AlloyDB PostgreSQL Port")
    alloydb_user: str = Field(default="postgres", description="AlloyDB User")
    alloydb_password: str = Field(default="CHANGE_ME_IN_PRODUCTION", description="AlloyDB Password")
    alloydb_database: str = Field(default="dronewatch_db", description="AlloyDB Database Name")

    # Video Stream Ingestion Parameters
    max_concurrent_streams: int = Field(default=4, ge=1, le=10)
    frame_sampling_fps: float = Field(
        default=1.0, description="Frames per second extracted for evaluation"
    )
    motion_sensitivity_threshold: float = Field(
        default=15.0, description="OpenCV motion delta threshold"
    )
    min_motion_area: int = Field(
        default=500, description="Minimum pixel contour area to trigger LLM analysis"
    )

    # Sample video file path for local simulation
    sample_video_path: str = Field(
        default="/home/jeffleinen/jeffdev/dronevideos/videos/S1002353.MP4",
        description="Default sample video file for local testing",
    )


def get_settings() -> Settings:
    """Return application settings instance."""
    return Settings()
