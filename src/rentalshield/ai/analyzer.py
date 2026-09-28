"""
Claude Vision damage analyzer.
Implements BaseAnalyzer using Anthropic Claude.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import cv2
import anthropic
from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

from rentalshield.ai.base import BaseAnalyzer
from rentalshield.models import Damage, DamageType, Severity, BoundingBox
from rentalshield.config import settings


def _is_retryable(exc: BaseException) -> bool:
    """Only retry on transient errors (rate-limit, 5xx) — not billing/auth."""
    if isinstance(exc, anthropic.RateLimitError):
        return True
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return True
    return False


# ── Shared prompt & parsing (also imported by GeminiAnalyzer) ─────────────────

_DAMAGE_PROMPT = """\
You are a strict professional car damage inspector reviewing a frame from a rental-car walkaround video.

YOUR TASK: Return a single JSON object (not an array) with this exact structure:
{
  "valid": true,
  "reason": "why the frame is valid or not",
  "plate": null,
  "view": "front",
  "damages": []
}

PLATE RULE: If a licence plate (number plate) is clearly readable in this photo,
write its exact text in "plate" (e.g. "EY 461TL", "B-7823-CK", "6KXH320").
If the plate is not visible or not legible, set "plate" to null.

VIEW RULE: Set "view" to the single best label for which part of the car this
photo primarily shows. Choose from exactly these values:
  "front"      — front bumper, grille, headlights, hood/bonnet
  "rear"       — rear bumper, boot/trunk lid, tail lights, rear window
  "left_side"  — driver side: left doors, left body panels, left mirror
  "right_side" — passenger side: right doors, right body panels, right mirror
  "roof"       — top of car, sunroof
  "wheels"     — close-up of tyre, alloy wheel, or wheel arch
  "interior"   — inside the car (seats, dashboard, steering wheel)
  "unknown"    — cannot determine from this photo
Set "view" even when valid is false.

STEP 1 — SET "valid" TO false AND "damages" TO [] IF ANY OF THESE ARE TRUE:
  • The rental car is NOT the dominant subject of the frame
    (i.e. the frame is mostly background — sky, trees, buildings, ground, parking lot)
  • The car is tiny or very far away — occupying less than 20% of the frame
  • The image is blurry, very dark, or overexposed so damage cannot be assessed
  • The frame shows only the car interior, tyres, or undercarriage

  IMPORTANT: Full-car shots (showing the whole vehicle or the entire rear/front/side)
  are VALID and must be inspected — the car fills most of the frame even if no single
  panel is zoomed in. Walkaround photos often show the entire rear or side.

  Background vehicles, people, or scenery are ALLOWED as long as the rental car
  is clearly the main subject filling most of the frame.

  If valid is false → stop here, damages must be [].

STEP 2 — ONLY IF valid IS true:
  The close-up car part in this frame IS the subject. Inspect it for:
  • Scratches  — surface paint marks or lines
  • Dents      — deformed / pushed-in body panels
  • Chips      — paint chips or stone chips
  • Cracks     — in bumpers, plastics, glass surrounds, trim
  • Scuffs     — paint transfer or surface abrasion
  • Rust       — corrosion spots or bubbling paint
  • Missing    — missing trim pieces, badges, caps, covers
  • OTHER      — use this type for: rubber seal or weatherstrip that is lifting,
                 loose or detached from glass or bodywork; this includes rear window
                 (backglass) rubber seals, windscreen seals, door window weatherstrips,
                 spoiler seals; trim strip peeling away; any structural/fit issue
                 that is not paint damage.

  Only report damage you are CONFIDENT is real physical damage on THIS car.
  Do NOT report: dirt, shadows, or compression artifacts.

  NEVER REPORT — these are optical effects, not damage:
  • Water droplets, rain marks, damp patches, or wet-paint reflections
  • Condensation, humidity streaks, or temporary moisture marks
  • Light glare, specular highlights, or bright reflections from sun or lamps
  A wet or glistening surface is NOT damage. Damage is a PERMANENT physical
  change to the paint or substrate — it does not clean off or dry away.

  WHITE / LIGHT-COLOURED PAINT (white, silver, cream, pearl): Real scratches and
  scuffs on light paint are often subtle — a grey streak, a faint darker line, or
  an area where the surface sheen or texture differs from the surrounding paint.
  Bumper scuffs typically look like a horizontal grey or dirty band.
  DO NOT skip marks just because they are faint — if you can clearly distinguish
  a mark from the base paint, it is damage and MUST be reported.

  LOCATION RULE — this is critical:
    Name the EXACT component that is damaged, not the broad body zone.
    WRONG: "rear quarter panel", "rear bumper area", "door area"
    RIGHT: "rear window bottom rubber seal", "fuel filler cap", "door handle",
           "tail light lens", "wheel arch plastic trim", "door sill chrome strip",
           "windscreen rubber seal", "rear bumper lower lip", "C-pillar trim",
           "rear window (backglass) rubber seal", "rear window side rubber seal",
           "rear spoiler rubber seal", "rear door window weatherstrip"
    Always include the side: "driver side", "passenger side", "rear left", "front right".
    For the rear window (backglass): say "rear window top/bottom/left/right rubber seal".

  Each damage entry in the "damages" array:
  {
    "type":        "SCRATCH | DENT | CHIP | CRACK | SCUFF | RUST | MISSING | OTHER",
    "location":    "exact component + side, e.g. 'rear window bottom rubber seal, passenger side'",
    "severity":    "MINOR | MODERATE | SEVERE",
    "description": "one concise sentence describing the actual physical damage",
    "confidence":  0.9,
    "x_pct": 0.0, "y_pct": 0.0, "w_pct": 0.0, "h_pct": 0.0
  }

  confidence: certainty this is real damage (0.0–1.0). Only include if ≥ 0.80.

  CRITICAL — silver, grey, and light-metallic paint is highly reflective.
  Reject the following false-positive patterns:
    • A faint tonal band along a body line = reflection, NOT a scratch
    • A dark curved area along a fender crease = shadow, NOT damage
    • A shiny spot on a bumper = highlight from sky/lamp, NOT paint chip
    • Uniform light patches on a panel = light from surroundings, NOT scuff
    • A single "dust-like" fleck = dirt, NOT chip — unless clearly gouged
  When in doubt, DO NOT REPORT. It is far better to miss a subtle scratch
  than to accuse the customer of damage that isn't there.

  HUMAN-ADDED ANNOTATIONS — IGNORE THESE COMPLETELY:
    • A black, red, or coloured circle drawn on the image (marker or app)
    • Arrows, hand-drawn lines, digital highlights, sticky-note style overlays
    • Any obviously artificial mark that is a perfect geometric shape
  These were added by a person to point at pre-existing marks. They are NOT
  themselves damage. Do NOT report the annotation or anything inside it
  unless you can INDEPENDENTLY see real damage (paint break, dent, chip)
  and describe it without referring to the drawn shape.

  BOUNDING BOX RULES — this must be right or the whole report is wrong:
    • The box must ENCLOSE ONLY the damage itself (10–25% of frame at most)
    • The box coordinates must match your description. If you say "front
      bumper", your y_pct must be in the LOWER half of the image; if you
      say "roof edge trim", y_pct must be in the UPPER half.
    • Before reporting, mentally re-project your bbox onto the image.
      If the region at those coordinates does NOT contain the damage you
      described, drop the entry — your coordinates are wrong.

  SEVERITY RULES — apply these strictly:
  MINOR    — hairline or very faint mark, under ~5 cm, no paint transfer from
             another object, likely removed by machine polish alone.
  MODERATE — clearly visible to the naked eye; OR paint transfer present
             (e.g. black rubber / tyre marks on white paint, colour deposit
             from another car); OR dent with no paint break but needing filler;
             OR scratch that has cut through the clear coat.
             Paint transfer ALWAYS means MODERATE minimum — it requires
             chemical treatment or respray regardless of size.
  SEVERE   — deep gouge through to primer or bare metal; large area (> 30 cm);
             structural deformation; cracked or broken plastic; missing part.

BOUNDING BOX: all values MUST be DECIMAL FRACTIONS 0.0–1.0 (not pixels, not percentages).
  Example: damage at pixel (216, 480) in a 1080×1920 image → x_pct=0.20, y_pct=0.25

Reply with ONLY the raw JSON object — no markdown, no explanation, nothing else."""

# Zone-analysis variant — same prompt but with a lower confidence threshold.
# Used when the image is already a tight crop of one car area, so borderline
# detections are worth surfacing (the crop validator catches remaining FPs).
_DAMAGE_PROMPT_ZONE = _DAMAGE_PROMPT.replace(
    "confidence: certainty this is real damage (0.0–1.0). Only include if ≥ 0.80.",
    (
        "confidence: certainty this is real damage (0.0–1.0). Include if ≥ 0.70 — "
        "this is a zoomed crop of one section of the car. Report EVERY visible damage: "
        "paint breaks, scratches, gouges, dents, chips, paint transfer, seal/trim defects. "
        "Include minor/faint marks. Even hairline scratches and small chips must be reported. "
        "DO NOT report: reflections, highlights, shadows, dust, or normal panel curvature."
    ),
)


def _frame_to_b64(frame: "cv2.Mat") -> str:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.standard_b64encode(buf).decode("utf-8")


_VALID_VIEWS = {
    "front", "rear", "left_side", "right_side",
    "roof", "wheels", "interior", "unknown",
}


def _parse_response(
    raw: str, frame_no: int, time_sec: float, min_confidence: float = 0.65
) -> "tuple[list[Damage], str | None, str | None]":
    """Parse JSON response (shared by Claude and Gemini analyzers).

    Returns (damages, plate, view) where:
      plate — licence plate text if visible in this photo, else None
      view  — which part of the car the photo shows (e.g. "front", "rear",
              "left_side", "right_side", "roof", "wheels"), or None
    Both are extracted from the same API call — no extra API call needed.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    parsed = json.loads(raw)

    plate: str | None = None
    view:  str | None = None

    # New format: {"valid": bool, "reason": str, "plate": "...", "view": "...", "damages": [...]}
    if isinstance(parsed, dict):
        # Extract view regardless of valid flag — helps coverage tracking even for
        # photos the AI rejects as "not a close-up" (they still show some car angle).
        view_raw = parsed.get("view")
        if view_raw and isinstance(view_raw, str):
            v = view_raw.strip().lower()
            if v in _VALID_VIEWS and v != "unknown":
                view = v

        if not parsed.get("valid", True):
            logger.debug(
                "Frame {} ({:.1f}s) rejected — {}",
                frame_no, time_sec, parsed.get("reason", "not a close-up car panel"),
            )
            return [], None, view
        # Extract plate if the AI found one
        plate_raw = parsed.get("plate")
        if plate_raw and isinstance(plate_raw, str):
            candidate = plate_raw.strip().upper()
            if len(candidate) >= 4:   # minimum sensible plate length
                plate = candidate
        items: list[dict[str, Any]] = parsed.get("damages", [])
    else:
        # Legacy array format (Claude / older responses)
        items = parsed
    damages = []
    seen_keys: set[tuple] = set()   # dedup: (type, normalised_location) per frame
    for item in items:
        try:
            # Normalise bbox values → always 0.0–1.0 regardless of what the model returns.
            # Models vary:
            #   • correct  → 0.0–1.0  (no change needed)
            #   • percent  → 0–100    (divide by 100)
            #   • pixels   → 0–2000+  (divide by 2000, a safe max image dimension)
            def _norm(v: float) -> float:
                v = float(v)
                if v <= 1.0:
                    return v           # already 0–1 fraction
                elif v <= 100.0:
                    return v / 100.0   # percentage format
                else:
                    return min(0.99, v / 2000.0)  # pixel coordinate

            confidence = float(item.get("confidence", 1.0))
            if confidence < min_confidence:
                logger.debug(
                    "Skipping low-confidence ({:.0%}) detection: {} — {}",
                    confidence, item.get("type"), item.get("location"),
                )
                continue

            bbox = BoundingBox(
                x_pct=_norm(item.get("x_pct", 0.1)),
                y_pct=_norm(item.get("y_pct", 0.1)),
                w_pct=_norm(item.get("w_pct", 0.2)),
                h_pct=_norm(item.get("h_pct", 0.2)),
            )
            # ── Bounding box sanity check ────────────────────────────────
            # Real damages are localised. A bbox covering more than 30% of the
            # image is the model waving at half the car — almost always wrong.
            # Also reject degenerate boxes (zero or near-zero area).
            _bbox_area = max(0.0, bbox.w_pct) * max(0.0, bbox.h_pct)
            if _bbox_area > 0.30:
                logger.info(
                    "Skipping oversized bbox ({:.0%} of frame): {} — {}",
                    _bbox_area, item.get("type"), item.get("location"),
                )
                continue
            if _bbox_area < 0.0005:
                logger.debug(
                    "Skipping degenerate bbox ({:.4%} of frame): {} — {}",
                    _bbox_area, item.get("type"), item.get("location"),
                )
                continue

            # ── Reject descriptions that reference human annotations ────
            # e.g. "highlighted by the black circle", "shown by the red arrow".
            # The AI is looking at a user-drawn mark, not real damage.
            _desc_low = (item.get("description") or "").lower()
            _ANNOTATION_KEYWORDS = (
                "highlighted by", "circled", "circle indicates",
                "marked by", "marked with", "arrow points", "the red arrow",
                "the black circle", "the red circle", "the yellow circle",
                "annotation", "highlighter",
            )
            if any(kw in _desc_low for kw in _ANNOTATION_KEYWORDS):
                logger.info(
                    "Skipping damage that describes a human annotation: {} — '{}'",
                    item.get("location"), item.get("description")[:80],
                )
                continue

            dmg = Damage(
                type        = DamageType(item["type"]),
                location    = item["location"],
                severity    = Severity(item.get("severity", "UNKNOWN")),
                description = item["description"],
                confidence  = confidence,
                frame       = frame_no,
                time_sec    = time_sec,
                bbox        = bbox,
            )
            # Dedup: skip if same type+location already seen in this frame
            dedup_key = (dmg.type, dmg.location.lower().strip())
            if dedup_key in seen_keys:
                logger.debug(
                    "Dedup: dropping duplicate '{} — {}' in frame {}",
                    dmg.type.value, dmg.location, frame_no,
                )
                continue
            seen_keys.add(dedup_key)
            damages.append(dmg)
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed damage entry: {}  ({})", item, exc)
    return damages, plate, view


# ── Claude implementation ─────────────────────────────────────────────────────

class DamageAnalyzer(BaseAnalyzer):
    """Damage analyzer powered by Anthropic Claude."""

    def __init__(self, api_key: str | None = None):
        key = api_key or settings.anthropic_api_key
        if not key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set. Copy .env.example → .env."
            )
        self._client       = anthropic.Anthropic(api_key=key)
        self._model        = settings.claude_model
        self.last_seen_plate: str | None = None   # set when plate is spotted in a frame
        self.last_seen_view:  str | None = None   # set to the car angle seen in each frame
        logger.info("Claude analyzer ready  (model: {})", self._model)

    @retry(
        retry   = lambda retry_state: _is_retryable(retry_state.outcome.exception()),
        stop    = stop_after_attempt(3),
        wait    = wait_exponential(multiplier=1, min=2, max=15),
        reraise = True,
    )
    def analyze_frame(
        self,
        frame:            "cv2.Mat",
        frame_no:         int   = 0,
        time_sec:         float = 0.0,
        skip_edge_filter: bool  = False,   # accepted for API compat; unused in Claude
        is_zone:          bool  = False,
    ) -> list[Damage]:
        logger.debug("Claude: analyzing frame {} ({:.1f}s) …", frame_no, time_sec)
        prompt   = _DAMAGE_PROMPT_ZONE if is_zone else _DAMAGE_PROMPT
        min_conf = 0.55 if is_zone else 0.65

        msg = self._client.messages.create(
            model      = self._model,
            max_tokens = settings.claude_max_tokens,
            messages   = [{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": "image/jpeg",
                                "data": _frame_to_b64(frame)}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        raw = msg.content[0].text
        try:
            damages, plate, view = _parse_response(raw, frame_no, time_sec,
                                                   min_confidence=min_conf)
            if plate:
                self.last_seen_plate = plate
            if view:
                self.last_seen_view = view
            return damages
        except json.JSONDecodeError as exc:
            logger.error("JSON parse failed for frame {} — {!r} ({})",
                         frame_no, raw[:200], exc)
            return []

    def generate_text(self, prompt: str) -> str:
        """Text-only generation — used by pdf_parser and reconciler."""
        msg = self._client.messages.create(
            model      = self._model,
            max_tokens = 2048,
            messages   = [{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
