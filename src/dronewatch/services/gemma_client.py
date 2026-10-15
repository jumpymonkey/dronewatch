"""Tier 1 Gemma 4 vision triage client for Google Cloud Run (Option A: vLLM)."""

import base64
import logging
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from dronewatch.config import Settings
from dronewatch.models.triage import GemmaTriageResponse

logger = logging.getLogger(__name__)

# Keywords triggering Tier 2 Gemini escalation
ALERT_KEYWORDS: frozenset[str] = frozenset(
    {
        "alert",
        "suspicious",
        "anomalous",
        "anomaly",
        "intruder",
        "unauthorized",
        "trespass",
        "trespassing",
        "breach",
        "danger",
        "hazard",
        "threat",
        "weapon",
        "climbing",
        "fire",
        "smoke",
        "loitering",
    }
)

BENIGN_KEYWORDS: frozenset[str] = frozenset(
    {
        "safe",
        "normal",
        "benign",
        "clear",
        "empty",
        "routine",
        "authorized",
        "pedestrian",
        "walkway",
    }
)


class GemmaTriageClient:
    """Async client communicating with Gemma 4 on Cloud Run (Option A: vLLM)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        """Initialize Tier 1 Gemma 4 triage client.

        Args:
            settings: DroneWatch application settings.
            client: Optional httpx.AsyncClient instance for testing / reuse.
        """
        self.settings = settings
        self.service_url = settings.gemma_service_url.strip()
        self.model_name = settings.gemma_model_name
        self.threshold = settings.gemma_triage_threshold
        self.timeout = settings.gemma_timeout_seconds
        self.prompt = settings.gemma_triage_prompt

        # Determine target endpoint (vLLM OpenAI-compatible endpoint)
        if self.service_url:
            parsed = urlparse(self.service_url)
            self.audience = f"{parsed.scheme}://{parsed.netloc}"
            if "/v1/" not in parsed.path:
                self.endpoint = f"{self.service_url.rstrip('/')}/v1/chat/completions"
            else:
                self.endpoint = self.service_url
        else:
            self.audience = ""
            self.endpoint = ""

        # Initialize or reuse HTTP client
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=2.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
        self._owns_client = client is None

        # Cached OIDC token state
        self._cached_token: str | None = None
        self._token_expiry_timestamp: float = 0.0

        # Circuit breaker state
        self._circuit_tripped: bool = False

    async def aclose(self) -> None:
        """Close underlying HTTP client resources."""
        if self._owns_client and not self._client.is_closed:
            await self._client.aclose()

    def _get_oidc_token(self) -> str | None:
        """Fetch Google IAM OIDC token for Cloud Run service-to-service auth."""
        now = time.time()
        if self._cached_token and now < self._token_expiry_timestamp:
            return self._cached_token

        if not self.audience:
            return None

        # 1. On Cloud Run / GCP environments, fetch directly from metadata server
        if os.environ.get("K_SERVICE") or os.environ.get("GAE_SERVICE"):
            try:
                import google.auth.transport.requests
                import google.oauth2.id_token

                auth_req = google.auth.transport.requests.Request()
                token = google.oauth2.id_token.fetch_id_token(auth_req, self.audience)
                self._cached_token = token
                # Refresh token 5 minutes before typical 60m expiry
                self._token_expiry_timestamp = now + 3300.0
                return token
            except Exception as ex:
                logger.warning("Could not acquire Google OIDC token in GCP environment: %s", ex)
                return None

        # 2. Local development fallback: try gcloud auth print-identity-token
        # without metadata timeout
        try:
            import shutil
            import subprocess

            if shutil.which("gcloud"):
                token = subprocess.check_output(
                    ["gcloud", "auth", "print-identity-token"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()
                if token:
                    self._cached_token = token
                    self._token_expiry_timestamp = now + 1800.0
                    return token
        except Exception as sub_ex:
            logger.debug("Could not acquire fallback identity token via gcloud: %s", sub_ex)

        return None

    def _parse_triage_text(self, text: str) -> tuple[bool, float, list[str]]:
        """Parse raw model output to determine threat classification and score.

        Args:
            text: Raw generated output string from Gemma 4.
        Returns:
            Tuple of (is_alert, confidence_score, matching_tags).
        """
        cleaned = text.lower().strip()
        matched_alerts = [kw for kw in ALERT_KEYWORDS if kw in cleaned]
        matched_benign = [kw for kw in BENIGN_KEYWORDS if kw in cleaned]

        terminal_safe = bool(re.search(r"\bsafe[\.!]?$", cleaned))
        terminal_alert = bool(re.search(r"\balert[\.!]?$", cleaned))
        critical_threats = [
            k
            for k in ("breach", "danger", "intruder", "weapon", "trespass", "climbing")
            if k in cleaned
        ]

        if terminal_safe and not critical_threats:
            benign_tags = ["safe"] + [kw for kw in matched_benign if kw != "safe"]
            return False, 0.05, benign_tags

        if terminal_alert or critical_threats:
            base_score = 0.95 if critical_threats else 0.85
            tags = matched_alerts if matched_alerts else ["alert"]
            return True, min(1.0, base_score), tags

        if matched_alerts:
            base_score = 0.85
            return True, base_score, matched_alerts

        if matched_benign:
            return False, 0.05, matched_benign

        # Default fallback if response is ambiguous
        return False, 0.20, ["unclassified"]

    async def triage_frame(
        self,
        frame_bytes: bytes,
        drone_id: str = "drone-unknown",
        timestamp_sec: float | None = None,
        request_scene_description: bool = False,
    ) -> GemmaTriageResponse:
        """Submit a single video frame to Tier 1 Gemma 4 for front-line triage.

        Implements fail-open circuit breaker: on timeout or error, returns
        CIRCUIT_BREAKER_BYPASS with escalate_to_gemini=True.

        Args:
            frame_bytes: JPEG/PNG encoded image bytes.
            drone_id: Identifier of the drone capturing the frame.
            timestamp_sec: Optional video position timecode.
            request_scene_description: If True, prompt Gemma 4 for a concise scene
                summary and safe/alert verdict (for periodic UI telemetry heartbeat).

        Returns:
            GemmaTriageResponse evaluated against threshold.
        """
        start_time = time.perf_counter()

        # If service URL is unset, fail open directly to Gemini
        if not self.endpoint:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return GemmaTriageResponse(
                escalate_to_gemini=True,
                anomaly_detected=True,
                triage_score=1.0,
                tier1_latency_ms=latency_ms,
                tier1_decision="CIRCUIT_BREAKER_BYPASS",
                tags=["service_url_not_configured"],
                raw_output=None,
                scene_description=None,
                model_name=self.model_name,
            )

        try:
            # Encode frame to Base64 data URI
            b64_image = base64.b64encode(frame_bytes).decode("ascii")

            prompt_text = (
                self.settings.gemma_scene_description_prompt
                if request_scene_description
                else self.prompt
            )
            max_tokens = 64 if request_scene_description else 32

            # Format OpenAI Vision / vLLM compatible payload (Option A)
            payload: dict[str, Any] = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_image}",
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": max_tokens,
                "temperature": 0.0,
            }

            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"DroneWatch-Ingestion/2.0 ({drone_id})",
            }

            # Inject Google OIDC token if available
            oidc_token = self._get_oidc_token()
            if oidc_token:
                headers["Authorization"] = f"Bearer {oidc_token}"

            response = await self._client.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            if self._circuit_tripped:
                logger.info(
                    "Tier 1 Gemma triage service recovered and resumed normal operation (200 OK)."
                )
                self._circuit_tripped = False

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Extract generated content from choices
            choices = data.get("choices", [])
            raw_content = ""
            if choices and "message" in choices[0]:
                raw_content = choices[0]["message"].get("content", "")
            elif "output" in data:
                raw_content = str(data["output"])

            is_alert, score, tags = self._parse_triage_text(raw_content)
            escalate = score >= self.threshold

            decision: str
            if not escalate:
                decision = "BENIGN"
            elif score >= 0.8:
                decision = "ANOMALOUS"
            else:
                decision = "SUSPICIOUS"

            scene_description: str | None = None
            if request_scene_description and raw_content:
                cleaned_desc = re.sub(
                    r"[\s\.,;:-]+(?:SAFE|ALERT|safe|alert)\.?$", "", raw_content
                ).strip()
                if cleaned_desc and not cleaned_desc.endswith("."):
                    cleaned_desc += "."
                scene_description = (
                    cleaned_desc if cleaned_desc else "Routine aerial surveillance - zone clear."
                )

            logger.info(
                "Tier 1 Gemma vision triage [%s]: prompt='%s' | response='%s' | "
                "verdict=%s score=%.2f tags=%s (latency=%.1fms)",
                drone_id,
                prompt_text,
                raw_content.strip(),
                decision,
                score,
                tags,
                latency_ms,
            )

            return GemmaTriageResponse(
                escalate_to_gemini=escalate,
                anomaly_detected=is_alert,
                triage_score=score,
                tier1_latency_ms=latency_ms,
                tier1_decision=decision,  # type: ignore[arg-type]
                tags=tags,
                raw_output=raw_content,
                scene_description=scene_description,
                model_name=self.model_name,
            )

        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as exc:
            # Circuit breaker: fail open to Gemini on timeout or HTTP 5xx
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            if not self._circuit_tripped:
                logger.warning(
                    "Tier 1 Gemma triage service degraded/failed (%s: %s). "
                    "Tripping circuit breaker to fail open.",
                    type(exc).__name__,
                    exc,
                )
                self._circuit_tripped = True
            else:
                logger.debug(
                    "Tier 1 Gemma triage service still degraded (%s: %s). Failing open.",
                    type(exc).__name__,
                    exc,
                )
            return GemmaTriageResponse(
                escalate_to_gemini=True,
                anomaly_detected=True,
                triage_score=1.0,
                tier1_latency_ms=latency_ms,
                tier1_decision="CIRCUIT_BREAKER_BYPASS",
                tags=["circuit_breaker_fail_open"],
                raw_output=str(exc),
                model_name=self.model_name,
            )
        except Exception as unexpected:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error("Unexpected error in Tier 1 triage: %s", unexpected, exc_info=True)
            return GemmaTriageResponse(
                escalate_to_gemini=True,
                anomaly_detected=True,
                triage_score=1.0,
                tier1_latency_ms=latency_ms,
                tier1_decision="CIRCUIT_BREAKER_BYPASS",
                tags=["circuit_breaker_unexpected_error"],
                raw_output=str(unexpected),
                model_name=self.model_name,
            )
