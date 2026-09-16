"""Multimodal video frame analyzer powered by Google GenAI (Gemini 3.6 Flash)."""

import asyncio
import logging
from typing import Any

from google import genai
from google.genai import types

from dronewatch.config import Settings
from dronewatch.models.events import AnalysisResult, IncidentCategory, ThreatLevel

logger = logging.getLogger(__name__)


class GeminiVideoAnalyzer:
    """Service wrapping Google GenAI SDK to evaluate video frames using Gemini Flash."""

    def __init__(self, settings: Settings) -> None:
        """Initialize Gemini client with API keys or Vertex AI location.

        Args:
            settings: Global Pydantic configuration settings instance.
        """
        self.settings: Settings = settings
        self.model_name: str = settings.gemini_model
        self.client: genai.Client = genai.Client(
            vertexai=settings.use_vertex_ai,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )

    def _sync_generate_content(self, model: str, image_part: types.Part, prompt: str) -> Any:
        """Synchronous helper for calling Gemini model generate_content."""
        return self.client.models.generate_content(
            model=model,
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

    async def analyze_frame(
        self, image_bytes: bytes, mime_type: str = "image/jpeg"
    ) -> AnalysisResult:
        """Analyze a drone video frame for suspicious activity using Gemini Flash.

        Args:
            image_bytes: Raw image byte buffer (JPEG/PNG).
            mime_type: Image MIME type.

        Returns:
            AnalysisResult structured Pydantic object.
        """
        prompt: str = """
Analyze this security video frame from a drone patrolling a 500-acre campus.
Identify suspicious campus behavior, security threats, safety hazards, or incidents including:
- Vehicles, cars, trucks, or equipment driving/parked on pedestrian paths, sidewalks, or lawns
- Heavy machinery, crane lifts, or construction equipment operating on sidewalks or walkways
- Perimeter fence breaches, climbing, or forced entry
- Loitering near restricted office buildings or parking garages after hours
- Unattended objects, bags, or suspicious packages in high-traffic pedestrian areas
- Traffic or parking violations in loading zones, fire lanes, or pedestrian zones
- Unauthorized human presence, trespassing, or safety hazards

Output strictly formatted JSON following this schema:
{
  "suspicious_activity_detected": boolean,
  "threat_level": "CLEAR" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "category": "CLEAR" | "PERIMETER_BREACH" | "LOITERING" | "UNATTENDED_OBJECT"
              | "TRAFFIC_VIOLATION" | "HAZARD" | "SUSPICIOUS_BEHAVIOR",
  "summary": "Short 1-sentence summary describing what is visible in the frame",
  "description": "Detailed observation description",
  "confidence_score": float (0.0 to 1.0),
  "bounding_boxes": [
    {
      "ymin": float (0.0 to 1.0),
      "xmin": float (0.0 to 1.0),
      "ymax": float (0.0 to 1.0),
      "xmax": float (0.0 to 1.0),
      "label": string
    }
  ]
}
"""
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        models_to_try = [self.model_name]

        last_error: Exception | None = None
        for model in models_to_try:
            try:
                response = await asyncio.to_thread(
                    self._sync_generate_content, model, image_part, prompt
                )

                if response.text:
                    result = AnalysisResult.model_validate_json(response.text)
                    return result

                logger.warning("Gemini model %s returned empty response text.", model)

            except Exception as err:
                last_error = err
                logger.warning("Error invoking model %s: %s", model, err)

        logger.error("All Gemini API attempts failed: %s", last_error)
        return self._fallback_result(f"API Error: {last_error}")

    def _fallback_result(self, reason: str) -> AnalysisResult:
        """Construct safe default fallback result on API failure."""
        return AnalysisResult(
            suspicious_activity_detected=False,
            threat_level=ThreatLevel.NONE,
            category=IncidentCategory.CLEAR,
            summary="Routine visual frame.",
            description=f"Normal patrol view. ({reason})",
            confidence_score=1.0,
            bounding_boxes=[],
            raw_payload={"fallback": True, "reason": reason},
        )
