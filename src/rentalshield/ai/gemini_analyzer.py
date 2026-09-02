"""
Gemini Vision damage analyzer.
Uses Google Gemini Flash — free tier covers typical rental scan volumes.

Free tier limits (gemini-3.5-flash, thinking enabled):
  • ~3–5 requests/minute (thinking model consumes many tokens per call)
  • 1,500 requests / day
  • No credit card required

Rate-limit strategy:
  • Per-frame: 4 retry attempts with 60 / 90 / 120 / 150s waits
  • Cross-frame: after any 429, impose a 65s cooldown before the NEXT frame
    so we never immediately 429 on back-to-back calls.

Get your key at: https://aistudio.google.com/app/apikey
"""

from __future__ import annotations

import time

import cv2
from google import genai
from google.genai import types
from loguru import logger

from rentalshield.ai.base import BaseAnalyzer
from rentalshield.ai.analyzer import _DAMAGE_PROMPT, _DAMAGE_PROMPT_ZONE, _parse_response
from rentalshield.models import Damage
from rentalshield.config import settings

# Seconds to wait before each new frame after a rate-limit event.
# The free-tier thinking model saturates the per-minute token budget
# with a single call; 65s ensures we slide into the next minute window.
_COOLDOWN_AFTER_429 = 65


class GeminiAnalyzer(BaseAnalyzer):
    """
    Damage analyzer powered by Google Gemini.
    Default model: gemini-3.5-flash (free tier, vision + thinking capable).
    """

    def __init__(
        self,
        api_key:    str | None = None,
        model:      str | None = None,
        text_model: str | None = None,
    ):
        key = api_key or settings.gemini_api_key
        if not key:
            raise EnvironmentError(
                "GEMINI_API_KEY not set.\n"
                "Get a free key at https://aistudio.google.com/app/apikey\n"
                "then add it to your .env file."
            )

        # Only retry on 429 (rate-limit). Do NOT retry 503/500/502/504 — those
        # are server-busy errors that will hang for minutes with exponential
        # backoff. We handle 429 ourselves in analyze_frame with a longer wait.
        # timeout=30000 ms = 30s hard HTTP deadline — prevents the library from
        # hanging indefinitely when the server is slow or drops the connection.
        self._client = genai.Client(
            api_key      = key,
            http_options = types.HttpOptions(
                timeout       = 30000,   # 30 seconds in milliseconds
                retry_options = types.HttpRetryOptions(
                    http_status_codes = [429],
                    attempts          = 1,   # no retries — we retry in analyze_frame
                ),
            ),
        )
        self._model       = model      or settings.gemini_model
        self._text_model  = text_model or settings.gemini_text_model
        # Timestamp until which the next frame call must wait (cross-frame cooldown)
        self._next_ok_at: float = 0.0
        # Thread-local storage so parallel photo scans don't stomp each other's state.
        # Each worker thread reads/writes its OWN last_seen_view/plate.
        import threading as _th
        self._tls = _th.local()

        # Shared generation config used for every vision call.
        # temperature=0  → greedy decoding, fully deterministic output.
        # thinking_budget=0 → disables chain-of-thought (saves ~90% of quota).
        self._vision_config = types.GenerateContentConfig(
            temperature     = 0,
            thinking_config = types.ThinkingConfig(thinking_budget=0),
        )
        logger.info("Gemini ready  (vision: {}  text: {}  temp: 0)",
                    self._model, self._text_model)

    # Thread-local view/plate — each parallel worker has its own value
    @property
    def last_seen_plate(self) -> "str | None":
        return getattr(self._tls, "plate", None)

    @last_seen_plate.setter
    def last_seen_plate(self, v: "str | None") -> None:
        self._tls.plate = v

    @property
    def last_seen_view(self) -> "str | None":
        return getattr(self._tls, "view", None)

    @last_seen_view.setter
    def last_seen_view(self, v: "str | None") -> None:
        self._tls.view = v

    def _preflight_wait(self, frame_no: int) -> None:
        """Sleep until the cross-frame cooldown expires (if any)."""
        remaining = self._next_ok_at - time.time()
        if remaining > 0:
            logger.info(
                "Frame {} — rate-limit cooldown: waiting {:.0f}s before call …",
                frame_no, remaining,
            )
            time.sleep(remaining)

    def analyze_frame(
        self,
        frame:            "cv2.Mat",
        frame_no:         int   = 0,
        time_sec:         float = 0.0,
        skip_edge_filter: bool  = False,
        is_zone:          bool  = False,
    ) -> list[Damage]:
        """Send a video frame (or photo) to Gemini and return detected damages.

        Parameters
        ----------
        skip_edge_filter : if True, bypass the edge-density pre-filter.
            Always False for video frames (noisy non-car scenes must be dropped).
            Must be True for photo mode — deliberate walkaround photos are dense
            by design and would otherwise all be rejected.
        """

        # Honor cross-frame cooldown set by the previous call's rate-limit
        self._preflight_wait(frame_no)
        logger.debug("Gemini: analyzing frame {} ({:.1f}s) …", frame_no, time_sec)

        # ── Fast pre-filter (no API call) ────────────────────────────────────
        # High edge density means the frame is a complex scene (trees, buildings,
        # a panned-away parking lot) rather than a close-up car panel.
        # Threshold tuned on this dataset: bad frames ≥ 0.058, good frames ≤ 0.052.
        # Photos bypass this — a deliberate 12 MP car shot is intentionally dense.
        if not skip_edge_filter:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = float(edges.sum()) / 255.0 / edges.size
            if edge_density > 0.057:
                logger.debug(
                    "Frame {} ({:.1f}s) skipped — high edge density {:.3f} (not a car panel close-up)",
                    frame_no, time_sec, edge_density,
                )
                return []

        # Encode frame as JPEG bytes
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        img_bytes = buf.tobytes()

        prompt   = _DAMAGE_PROMPT_ZONE if is_zone else _DAMAGE_PROMPT
        # Lowered from 0.70/0.80 → 0.65/0.75 to handle compressed images better.
        # WhatsApp compression loses detail, so we need to be more permissive.
        # This helps compressed-image detection without hurting high-quality scans.
        min_conf = 0.65 if is_zone else 0.75

        for attempt in range(4):
            try:
                response = self._client.models.generate_content(
                    model    = self._model,
                    contents = [
                        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                        prompt,
                    ],
                    config   = self._vision_config,
                )
                raw = response.text.strip()
                # Success — clear any pending cooldown
                self._next_ok_at = 0.0
                damages, plate, view = _parse_response(raw, frame_no, time_sec,
                                                       min_confidence=min_conf)
                if plate:
                    self.last_seen_plate = plate
                if view:
                    self.last_seen_view = view
                return damages

            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str:
                    # Per-attempt back-off: 60 → 90 → 120 → 150s
                    wait = 60 * (attempt + 1)
                    # Also schedule a cross-frame cooldown so the NEXT frame
                    # doesn't immediately hit the limit again.
                    self._next_ok_at = time.time() + wait + _COOLDOWN_AFTER_429
                    logger.warning(
                        "Gemini rate-limit on frame {} (attempt {}/{}) — waiting {}s …",
                        frame_no, attempt + 1, 4, wait,
                    )
                    time.sleep(wait)
                    continue
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    # Server busy — short retry (max 2 attempts × 15s = 30s extra)
                    if attempt < 2:
                        logger.warning(
                            "Gemini 503 on frame {} (attempt {}/2) — waiting 15s …",
                            frame_no, attempt + 1,
                        )
                        time.sleep(15)
                        continue
                    # After 2 retries give up — don't block the scan
                    logger.error(
                        "Gemini error on frame {} ({:.1f}s): {}",
                        frame_no, time_sec, exc,
                    )
                    return []
                if "timed out" in err_str.lower() or "timeout" in err_str.lower():
                    # Network-level timeout — retry immediately (no wait needed)
                    if attempt < 2:
                        logger.warning(
                            "Gemini timeout on frame {} (attempt {}/2) — retrying …",
                            frame_no, attempt + 1,
                        )
                        continue
                    logger.error(
                        "Gemini error on frame {} ({:.1f}s): {}",
                        frame_no, time_sec, exc,
                    )
                    return []
                # Any other error: log and return empty (don't crash the scan)
                logger.error(
                    "Gemini error on frame {} ({:.1f}s): {}",
                    frame_no, time_sec, exc,
                )
                return []

        logger.error("Gemini: gave up on frame {} after 4 attempts", frame_no)
        return []

    def generate_text_with_image(self, frame: "cv2.Mat", prompt: str, timeout: float = 15.0) -> str:
        """Send one image + a text prompt; return the raw text response.

        503 errors propagate immediately (no library-level retry) because
        the client is configured with http_status_codes=[429] only.
        The timeout parameter is accepted for API compatibility but the
        actual timeout is controlled by the client's http_options.
        """
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        img_bytes = buf.tobytes()
        response = self._client.models.generate_content(
            model    = self._model,
            contents = [
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                prompt,
            ],
            config   = self._vision_config,
        )
        return response.text.strip()

    def generate_text(self, prompt: str) -> str:
        """Text-only generation — uses the lighter text model (separate quota)."""
        for attempt in range(6):
            try:
                response = self._client.models.generate_content(
                    model    = self._text_model,   # lighter model, own quota
                    contents = [prompt],
                )
                return response.text.strip()
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str:
                    wait = 15 * (attempt + 1)   # 15s, 30s, 45s, 60s, 75s, 90s
                    logger.warning("Gemini rate-limit (text) — waiting {}s …", wait)
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError("Gemini text generation failed after 6 attempts")
