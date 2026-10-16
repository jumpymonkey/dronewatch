"""Tier 1 Gemma 4 vision triage client for Google Cloud Run (Option A: vLLM)."""

import base64
import json
import logging
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from dronewatch.config import Settings
from dronewatch.models.events import (
    AnalysisResult,
    BoundingBox,
    IncidentCategory,
    ThreatLevel,
)
from dronewatch.models.triage import GemmaTriageResponse
from dronewatch.models.workflow_config import (
    DEFAULT_ALERT_KEYWORDS,
    DEFAULT_BENIGN_KEYWORDS,
    AmbiguityPolicy,
)

logger = logging.getLogger(__name__)

# Default keywords for backward compatibility with external imports
ALERT_KEYWORDS: frozenset[str] = DEFAULT_ALERT_KEYWORDS
BENIGN_KEYWORDS: frozenset[str] = DEFAULT_BENIGN_KEYWORDS


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

        # Determine target endpoint and audience
        self.endpoint, self.audience = self._resolve_endpoint_and_audience(self.service_url)

        # Initialize or reuse HTTP client
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=2.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
        self._owns_client = client is None

        # Cached OIDC token state
        self._cached_token: str | None = None
        self._cached_audience: str = ""
        self._token_expiry_timestamp: float = 0.0

        # Circuit breaker state
        self._circuit_tripped: bool = False

    @staticmethod
    def _resolve_endpoint_and_audience(service_url: str) -> tuple[str, str]:
        """Resolve OpenAI-compatible vLLM endpoint and audience from service URL."""
        cleaned = service_url.strip()
        if not cleaned:
            return "", ""
        parsed = urlparse(cleaned)
        audience = f"{parsed.scheme}://{parsed.netloc}"
        if "/v1/" not in parsed.path:
            endpoint = f"{cleaned.rstrip('/')}/v1/chat/completions"
        else:
            endpoint = cleaned
        return endpoint, audience

    async def aclose(self) -> None:
        """Close underlying HTTP client resources."""
        if self._owns_client and not self._client.is_closed:
            await self._client.aclose()

    def _get_oidc_token(self, target_audience: str | None = None) -> str | None:
        """Fetch Google IAM OIDC token for Cloud Run service-to-service auth."""
        aud = target_audience or self.audience
        if not aud:
            return None

        now = time.time()
        if (
            self._cached_token
            and now < self._token_expiry_timestamp
            and self._cached_audience == aud
        ):
            return self._cached_token

        # 1. On Cloud Run / GCP environments, fetch directly from metadata server
        if os.environ.get("K_SERVICE") or os.environ.get("GAE_SERVICE"):
            try:
                import google.auth.transport.requests
                import google.oauth2.id_token

                auth_req = google.auth.transport.requests.Request()
                token = google.oauth2.id_token.fetch_id_token(auth_req, aud)
                self._cached_token = token
                self._cached_audience = aud
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
                    self._cached_audience = aud
                    self._token_expiry_timestamp = now + 1800.0
                    return token
        except Exception as sub_ex:
            logger.debug("Could not acquire fallback identity token via gcloud: %s", sub_ex)

        return None

    def _parse_triage_text(
        self,
        text: str,
        alert_keywords: list[str] | set[str] | frozenset[str] | None = None,
        benign_keywords: list[str] | set[str] | frozenset[str] | None = None,
        ambiguity_policy: AmbiguityPolicy | str | None = None,
    ) -> tuple[bool, float, list[str]]:
        """Parse raw model output to determine threat classification and score.

        Args:
            text: Raw generated output string from Gemma 4.
            alert_keywords: Optional keywords triggering alert score.
            benign_keywords: Optional keywords indicating benign status.
            ambiguity_policy: Policy when output is ambiguous (FAIL_SAFE or CONSERVATIVE).

        Returns:
            Tuple of (is_alert, confidence_score, matching_tags).
        """
        cleaned = text.lower().strip()
        active_alerts = (
            [kw.lower() for kw in alert_keywords]
            if alert_keywords is not None
            else list(ALERT_KEYWORDS)
        )
        active_benign = (
            [kw.lower() for kw in benign_keywords]
            if benign_keywords is not None
            else list(BENIGN_KEYWORDS)
        )
        policy = (
            AmbiguityPolicy(ambiguity_policy)
            if ambiguity_policy is not None
            else AmbiguityPolicy.FAIL_SAFE
        )

        matched_alerts = [kw for kw in active_alerts if kw in cleaned]
        matched_benign = [kw for kw in active_benign if kw in cleaned]

        terminal_safe = bool(re.search(r"\bsafe[\.!]?$", cleaned))
        terminal_alert = bool(re.search(r"\balert[\.!]?$", cleaned))
        critical_threats = [
            k
            for k in ("breach", "danger", "intruder", "weapon", "trespass", "climbing")
            if k in cleaned
        ]

        if terminal_safe and not critical_threats and not matched_alerts:
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

        # Handling policy when output is ambiguous / unclassified
        if policy == AmbiguityPolicy.FAIL_SAFE:
            return True, 0.80, ["unclassified", "ambiguous_fail_safe"]
        return False, 0.20, ["unclassified", "ambiguous_conservative"]

    async def triage_frame(
        self,
        frame_bytes: bytes,
        drone_id: str = "drone-unknown",
        timestamp_sec: float | None = None,
        request_scene_description: bool = False,
        prompt: str | None = None,
        threshold: float | None = None,
        gemma_service_url: str | None = None,
        gemma_model: str | None = None,
        gemma_timeout_seconds: float | None = None,
        alert_keywords: list[str] | set[str] | frozenset[str] | None = None,
        benign_keywords: list[str] | set[str] | frozenset[str] | None = None,
        ambiguity_policy: AmbiguityPolicy | str | None = None,
        vllm_temperature: float | None = None,
        vllm_max_tokens: int | None = None,
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
            prompt: Optional dynamic prompt overriding default triage prompt.
            threshold: Optional dynamic confidence score threshold.
            gemma_service_url: Optional runtime service URL override.
            gemma_model: Optional runtime model identifier override.
            gemma_timeout_seconds: Optional runtime timeout in seconds.
            alert_keywords: Optional keywords triggering alert score.
            benign_keywords: Optional keywords indicating benign status.
            ambiguity_policy: Handling policy for unclassified outputs.
            vllm_temperature: Optional runtime sampling temperature.
            vllm_max_tokens: Optional runtime max output tokens.

        Returns:
            GemmaTriageResponse evaluated against threshold.
        """
        start_time = time.perf_counter()

        target_service_url = (gemma_service_url or "").strip() or self.service_url
        endpoint, audience = self._resolve_endpoint_and_audience(target_service_url)
        target_model = gemma_model or self.model_name
        target_timeout = (
            gemma_timeout_seconds if gemma_timeout_seconds is not None else self.timeout
        )

        # If service URL is unset, fail open directly to Gemini
        if not endpoint:
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
                model_name=target_model,
            )

        try:
            # Encode frame to Base64 data URI
            b64_image = base64.b64encode(frame_bytes).decode("ascii")

            if request_scene_description:
                prompt_text = self.settings.gemma_scene_description_prompt
                tokens = 64
            elif prompt is not None and prompt.strip():
                prompt_text = prompt
                tokens = vllm_max_tokens if vllm_max_tokens is not None else 32
            else:
                prompt_text = self.prompt
                tokens = vllm_max_tokens if vllm_max_tokens is not None else 32

            temp = vllm_temperature if vllm_temperature is not None else 0.0

            # Format OpenAI Vision / vLLM compatible payload (Option A)
            payload: dict[str, Any] = {
                "model": target_model,
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
                "max_tokens": tokens,
                "temperature": temp,
            }

            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"DroneWatch-Ingestion/2.0 ({drone_id})",
            }

            # Inject Google OIDC token if available
            oidc_token = self._get_oidc_token(audience)
            if oidc_token:
                headers["Authorization"] = f"Bearer {oidc_token}"

            response = await self._client.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=target_timeout,
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

            is_alert, score, tags = self._parse_triage_text(
                raw_content,
                alert_keywords=alert_keywords,
                benign_keywords=benign_keywords,
                ambiguity_policy=ambiguity_policy,
            )
            cutoff = threshold if threshold is not None else self.threshold
            escalate = score >= cutoff

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
                model_name=target_model,
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
                model_name=target_model,
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
                model_name=target_model,
            )

    def _extract_json_analysis(self, text: str) -> AnalysisResult | None:
        """Attempt to extract and validate JSON schema from Gemma response."""
        cleaned = text.strip()
        json_str: str | None = None
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if fence_match:
            json_str = fence_match.group(1).strip()
        else:
            first_brace = cleaned.find("{")
            last_brace = cleaned.rfind("}")
            if first_brace != -1 and last_brace > first_brace:
                json_str = cleaned[first_brace : last_brace + 1].strip()

        if not json_str:
            return None

        try:
            data = json.loads(json_str)
            if not isinstance(data, dict):
                return None

            raw_threat = str(data.get("threat_level", "CLEAR")).upper().strip()
            threat_mapping: dict[str, ThreatLevel] = {
                "CLEAR": ThreatLevel.NONE,
                "NONE": ThreatLevel.NONE,
                "LOW": ThreatLevel.LOW,
                "MEDIUM": ThreatLevel.MEDIUM,
                "HIGH": ThreatLevel.HIGH,
                "CRITICAL": ThreatLevel.CRITICAL,
            }
            threat_level = threat_mapping.get(raw_threat, ThreatLevel.NONE)

            raw_cat = str(data.get("category", "CLEAR")).upper().strip()
            category_mapping: dict[str, IncidentCategory] = {
                "CLEAR": IncidentCategory.CLEAR,
                "PERIMETER_BREACH": IncidentCategory.PERIMETER_BREACH,
                "LOITERING": IncidentCategory.LOITERING,
                "UNATTENDED_OBJECT": IncidentCategory.UNATTENDED_OBJECT,
                "TRAFFIC_VIOLATION": IncidentCategory.TRAFFIC_VIOLATION,
                "HAZARD": IncidentCategory.HAZARD,
                "SUSPICIOUS_BEHAVIOR": IncidentCategory.SUSPICIOUS_BEHAVIOR,
            }
            category = category_mapping.get(
                raw_cat,
                IncidentCategory.CLEAR
                if threat_level == ThreatLevel.NONE
                else IncidentCategory.SUSPICIOUS_BEHAVIOR,
            )

            suspicious = bool(data.get("suspicious_activity_detected", False))
            if threat_level == ThreatLevel.NONE:
                suspicious = False
                category = IncidentCategory.CLEAR
            elif not suspicious:
                threat_level = ThreatLevel.NONE
                category = IncidentCategory.CLEAR

            summary = str(data.get("summary", "")).strip()
            if not summary:
                summary = (
                    "Routine aerial surveillance - zone clear."
                    if threat_level == ThreatLevel.NONE
                    else f"{category.value} detected."
                )

            description = str(data.get("description", "")).strip() or summary

            try:
                confidence = float(data.get("confidence_score", 0.90))
                confidence = max(0.0, min(1.0, confidence))
            except (ValueError, TypeError):
                confidence = 0.90

            raw_boxes = data.get("bounding_boxes", [])
            bounding_boxes: list[BoundingBox] = []
            if isinstance(raw_boxes, list):
                for b in raw_boxes:
                    if isinstance(b, dict):
                        try:
                            bounding_boxes.append(BoundingBox.model_validate(b))
                        except Exception:
                            continue

            return AnalysisResult(
                suspicious_activity_detected=suspicious,
                threat_level=threat_level,
                category=category,
                summary=summary,
                description=description,
                confidence_score=confidence,
                bounding_boxes=bounding_boxes,
            )
        except Exception as parse_err:
            logger.debug("Failed to parse extracted JSON candidate from Gemma: %s", parse_err)
            return None

    def _parse_deep_analysis_text(self, text: str) -> AnalysisResult:
        """Parse natural language deep analysis text from Gemma 4 into structured AnalysisResult."""
        # 1. Primary: JSON structured extraction
        json_result = self._extract_json_analysis(text)
        if json_result is not None:
            return json_result

        # 2. Secondary: Fallback natural language text analysis
        cleaned = text.strip()
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        content_lines = [line for line in lines if not line.startswith("#")]
        content_text = " ".join(content_lines) if content_lines else cleaned
        lower = content_text.lower()

        # Check for explicit negation or clear statements
        has_negated_threat = bool(
            re.search(
                r"\b(?:no|zero|without|not)\s+(?:suspicious|threat|anomaly|breach|unauthorized|danger|hazard|incident|concern)s?\b",
                lower,
            )
        )

        threat_level = ThreatLevel.NONE
        category = IncidentCategory.CLEAR
        suspicious = False
        conf = 0.90

        if not has_negated_threat:
            if any(
                w in lower
                for w in ("active shooter", "weapon", "explosion", "armed person", "fire outbreak")
            ):
                threat_level = ThreatLevel.CRITICAL
                category = IncidentCategory.HAZARD
                suspicious = True
                conf = 0.95
            elif any(
                w in lower
                for w in (
                    "perimeter breach",
                    "forced entry",
                    "climbing fence",
                    "scaling fence",
                    "fence breach",
                )
            ):
                threat_level = ThreatLevel.HIGH
                category = IncidentCategory.PERIMETER_BREACH
                suspicious = True
                conf = 0.90
            elif any(
                eq in lower
                for eq in (
                    "equipment",
                    "machinery",
                    "vehicle",
                    "cart",
                    "lift",
                    "crane",
                    "forklift",
                    "tractor",
                    "obstruction",
                    "blocked",
                )
            ) and any(
                path in lower
                for path in (
                    "walkway",
                    "pedestrian",
                    "sidewalk",
                    "footpath",
                    "pathway",
                    "walking path",
                    "hallway",
                )
            ):
                threat_level = ThreatLevel.MEDIUM
                category = IncidentCategory.HAZARD
                suspicious = True
                conf = 0.85
            elif any(
                w in lower
                for w in (
                    "unauthorized person",
                    "trespassing",
                    "trespasser",
                    "loitering after hours",
                    "vehicle on walkway",
                )
            ):
                threat_level = ThreatLevel.MEDIUM
                category = IncidentCategory.SUSPICIOUS_BEHAVIOR
                suspicious = True
                conf = 0.85
            elif any(
                w in lower
                for w in (
                    "parking violation",
                    "traffic violation",
                    "unattended bag",
                    "suspicious package",
                )
            ):
                threat_level = ThreatLevel.LOW
                category = (
                    IncidentCategory.TRAFFIC_VIOLATION
                    if "traffic" in lower or "parking" in lower
                    else IncidentCategory.UNATTENDED_OBJECT
                )
                suspicious = True
                conf = 0.80

        # Boundary regex for explicit "all clear" or routine surveillance verdicts
        clear_pattern = (
            r"\b(all clear|zone clear|scene is clear|area is clear|"
            r"everything is clear|no activity detected|routine surveillance|patrol clear)\b"
        )
        is_explicitly_clear = bool(re.search(clear_pattern, lower))

        # Baseline: normal/benign if explicitly negated or clear
        if has_negated_threat or (not suspicious and is_explicitly_clear):
            threat_level = ThreatLevel.NONE
            category = IncidentCategory.CLEAR
            suspicious = False
            conf = 0.95

        if suspicious:
            first_sentence = (
                content_lines[0] if content_lines else "Suspicious campus activity detected."
            )
            summary = first_sentence.split(".")[0].strip() + "."
        else:
            summary = "Routine aerial surveillance - zone clear."

        return AnalysisResult(
            suspicious_activity_detected=suspicious,
            threat_level=threat_level,
            category=category,
            summary=summary,
            description=content_text if content_text else summary,
            confidence_score=conf,
            bounding_boxes=[],
        )

    async def deep_analyze_frame(
        self,
        frame_bytes: bytes,
        escalation_prompt: str,
        drone_id: str = "drone-unknown",
        gemma_service_url: str | None = None,
        gemma_model: str | None = None,
        gemma_timeout_seconds: float | None = None,
        vllm_temperature: float | None = None,
        vllm_max_tokens: int | None = None,
    ) -> AnalysisResult:
        """Perform Tier 2 deep contextual reasoning using Gemma 4 on Cloud Run.

        Args:
            frame_bytes: JPEG/PNG encoded image bytes.
            escalation_prompt: Contextual evaluation prompt guiding Gemma 4 analysis.
            drone_id: Calling drone identifier for telemetry logging.
            gemma_service_url: Optional runtime service URL override.
            gemma_model: Optional runtime model identifier override.
            gemma_timeout_seconds: Optional runtime timeout in seconds.
            vllm_temperature: Optional sampling temperature override.
            vllm_max_tokens: Optional max output tokens override.

        Returns:
            AnalysisResult structured representation.
        """
        start_time = time.perf_counter()

        target_service_url = (
            gemma_service_url.strip()
            if gemma_service_url and gemma_service_url.strip()
            else self.service_url
        )
        endpoint, audience = self._resolve_endpoint_and_audience(target_service_url)
        target_model = gemma_model or self.model_name
        target_timeout = (
            gemma_timeout_seconds if gemma_timeout_seconds is not None else self.timeout
        )

        if not endpoint:
            return self._fallback_deep_analysis("Gemma service URL not configured")

        try:
            b64_image = base64.b64encode(frame_bytes).decode("ascii")

            tokens = vllm_max_tokens if vllm_max_tokens is not None else 600
            temp = vllm_temperature if vllm_temperature is not None else 0.1

            payload: dict[str, Any] = {
                "model": target_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": escalation_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_image}",
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": tokens,
                "temperature": temp,
            }

            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"DroneWatch-Escalation/2.0 ({drone_id})",
            }
            oidc_token = self._get_oidc_token(audience)
            if oidc_token:
                headers["Authorization"] = f"Bearer {oidc_token}"

            response = await self._client.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=target_timeout,
            )
            response.raise_for_status()
            data = response.json()

            choices = data.get("choices", [])
            raw_content = ""
            if choices and "message" in choices[0]:
                raw_content = choices[0]["message"].get("content", "")
            elif "output" in data:
                raw_content = str(data["output"])

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            logger.info(
                "Tier 2 Gemma escalation [%s]: latency=%.1fms | response='%s'",
                drone_id,
                latency_ms,
                raw_content.strip(),
            )

            analysis = self._parse_deep_analysis_text(raw_content)
            analysis.model_name = target_model
            analysis.latency_ms = latency_ms
            analysis.raw_response = raw_content
            analysis.raw_payload = {
                "tier": 2,
                "model": target_model,
                "latency_ms": latency_ms,
                "raw_output": raw_content,
            }
            return analysis
        except Exception as err:
            logger.error("Tier 2 Gemma deep analysis error: %s", err)
            return self._fallback_deep_analysis(str(err))

    def _fallback_deep_analysis(self, reason: str) -> AnalysisResult:
        """Construct safe default result when Gemma deep analysis fails."""
        return AnalysisResult(
            suspicious_activity_detected=False,
            threat_level=ThreatLevel.NONE,
            category=IncidentCategory.CLEAR,
            summary="Routine visual frame (Gemma fallback).",
            description=f"Normal patrol view. Fallback reason: {reason}",
            confidence_score=0.5,
            bounding_boxes=[],
            raw_payload={"fallback": True, "reason": reason},
            model_name=self.model_name,
            latency_ms=0.0,
            raw_response=f"Fallback: {reason}",
        )
