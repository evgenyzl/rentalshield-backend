"""
Component identifier — second AI pass on each damage crop.

After the main damage scan names the broad zone ("rear quarter panel"),
this module sends the crop to the vision model with one focused question:
"What exact car component is this?" and returns a precise name like
"rear window rubber seal" or "fuel filler cap".

The result REPLACES damage.location with the specific component name,
keeping the position qualifier (passenger side / driver side) from the
original detection.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from loguru import logger

_COMPONENT_PROMPT = """\
You are a car-parts expert. This image shows a car with a red bounding box drawn around one specific damage area.

Look at the component INSIDE or TOUCHING the red box.
What is the EXACT name of that car component?

Pick the single best match from this list:
  rubber window seal / weatherstrip
  fuel filler cap / fuel flap
  tail light lens
  headlight lens
  door handle
  side mirror housing
  bumper lip / bumper panel
  body panel / quarter panel paint
  chrome trim strip
  wheel arch plastic trim
  door sill trim
  window glass
  C-pillar trim
  roof rail
  antenna
  badge / emblem
  licence plate surround
  wiper blade / wiper arm
  grille

Reply with ONLY the component name from the list above — no extra words, no punctuation."""

_MIN_GAP_S = 5.0   # respect the same rate-limit pacing as the crop validator


def identify_component(
    crop_path: Path,
    analyzer,
    _last_call: list | None = None,
) -> str | None:
    """
    Ask the vision model to name the specific car component in the crop.

    Returns the identified component string, or None on failure.
    _last_call is a [float] mutable used to pace calls ≥ _MIN_GAP_S apart.
    """
    if _last_call is None:
        _last_call = [0.0]

    # Pace calls
    gap = time.monotonic() - _last_call[0]
    if gap < _MIN_GAP_S:
        wait = _MIN_GAP_S - gap
        logger.debug("Component identifier: spacing {:.1f}s before next call …", wait)
        time.sleep(wait)

    _last_call[0] = time.monotonic()

    try:
        from google.genai import types
        import cv2

        frame = cv2.imread(str(crop_path))
        if frame is None:
            return None

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        img_bytes = buf.tobytes()

        client  = analyzer._client
        model   = analyzer._model
        config  = types.GenerateContentConfig(
            temperature     = 0,
            thinking_config = types.ThinkingConfig(thinking_budget=0),
        )

        response = client.models.generate_content(
            model    = model,
            contents = [
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                _COMPONENT_PROMPT,
            ],
            config   = config,
        )
        raw = response.text.strip().lower()
        logger.debug("Component ID for {}: '{}'", crop_path.name, raw)
        return raw

    except Exception as exc:
        msg = str(exc)
        is_quota = "429" in msg or "quota" in msg.lower() or "exhausted" in msg.lower()
        is_daily = "PerDay" in msg or "per_day" in msg.lower() or "daily" in msg.lower()

        if is_quota and is_daily:
            # Daily limit hit — retrying won't help; give up immediately
            logger.warning("Component ID: daily quota exhausted — skipping component identification")
            _last_call[0] = float("inf")  # signal callers to stop trying
            return None

        if is_quota:
            # Per-minute limit — wait and retry once
            delay = _parse_retry_delay(msg) or 65
            logger.warning("Component ID 429 — waiting {}s …", delay)
            time.sleep(delay)
            _last_call[0] = time.monotonic()
            try:
                response = client.models.generate_content(
                    model    = model,
                    contents = [
                        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                        _COMPONENT_PROMPT,
                    ],
                    config   = config,
                )
                return response.text.strip().lower()
            except Exception:
                pass

        logger.warning("Component ID failed for {}: {}", crop_path.name, exc)
        return None


def _parse_retry_delay(msg: str) -> int | None:
    m = re.search(r"retryDelay[\":\s]+(\d+)s", msg)
    if m:
        return int(m.group(1)) + 2
    m = re.search(r"retry after (\d+)", msg, re.IGNORECASE)
    if m:
        return int(m.group(1)) + 2
    return None


# Keywords that signal the location is already a specific component name.
# If ANY of these appear, skip the component-identifier pass entirely.
_SPECIFIC_KEYWORDS = {
    "rubber seal", "weatherstrip", "weather strip",
    "door handle", "handle cup",
    "fuel filler", "fuel cap", "fuel flap",
    "tail light", "taillight", "tail lamp",
    "headlight", "head light",
    "window glass",
    "chrome strip", "chrome trim",
    "wheel arch",
    "door sill",
    "bumper lip",
    "spoiler",
    "badge", "emblem",
    "wiper blade", "wiper arm",
    "grille",
    "antenna",
    "licence plate", "license plate",
    "c-pillar", "b-pillar", "a-pillar",
    "roof rail",
    "mirror housing", "side mirror",
    "trim strip", "trim piece",
}


def _is_specific_location(location: str) -> bool:
    """Return True if the location already names a precise component.

    When True, the component-identifier second pass is skipped — the
    original AI name is already good enough and we don't want to
    downgrade it to a generic category label.
    """
    loc = location.lower()
    return any(kw in loc for kw in _SPECIFIC_KEYWORDS)


def _extract_side(location: str) -> str:
    """Pull side qualifier from the original AI location string."""
    loc = location.lower()
    if "driver" in loc:
        return ", driver side"
    if "passenger" in loc:
        return ", passenger side"
    if "front left" in loc or "left front" in loc:
        return ", front left"
    if "front right" in loc or "right front" in loc:
        return ", front right"
    if "rear left" in loc or "left rear" in loc:
        return ", rear left"
    if "rear right" in loc or "right rear" in loc:
        return ", rear right"
    if "front" in loc:
        return ", front"
    if "rear" in loc:
        return ", rear"
    return ""


def refine_location(damage, analyzer, _last_call: list | None = None) -> str | None:
    """
    Run component identification on the full annotated frame (which has the red
    bounding box drawn) and return a refined location string like
    'rear window rubber seal, passenger side'.

    Uses full_img_path (annotated frame with red box) because the crop alone
    lacks context — the model needs to see where on the car the damage is.
    Falls back to img_path (crop) if full_img_path is unavailable.

    Returns None if identification fails.
    """
    # If the original AI already gave a specific component name, don't
    # override it with the generic category list from identify_component().
    if _is_specific_location(damage.location):
        logger.debug(
            "Component ID: location already specific — '{}', skipping",
            damage.location,
        )
        return None  # None = keep original location unchanged

    # Prefer the full annotated frame — it has spatial context + red box
    img = damage.full_img_path or damage.img_path
    if not img or not Path(img).exists():
        return None

    component = identify_component(Path(img), analyzer, _last_call)
    if not component:
        return None

    # Sanity check: reject refinements that are clearly from a different car zone.
    # The bbox coordinates from the primary AI are sometimes slightly off, causing
    # the component identifier to look at the wrong area (e.g. window instead of bumper).
    if not _refinement_is_plausible(damage.location, component):
        logger.debug(
            "Component ID: '{}' rejected as implausible refinement for '{}' — keeping original",
            component, damage.location,
        )
        return None

    side = _extract_side(damage.location)
    refined = component + side
    return refined


def _refinement_is_plausible(original_location: str, refined_component: str) -> bool:
    """
    Returns False when the refined component is clearly from a different part
    of the car than the original damage location — indicating the bounding box
    pointed to the wrong area and the component identifier was fooled.

    We check zone compatibility: body-panel locations should not become glass,
    wiper, or handle names; and vice versa.
    """
    orig = original_location.lower()
    ref  = refined_component.lower()

    # ── Zone definitions ──────────────────────────────────────────────────────
    orig_is_bumper        = "bumper" in orig
    orig_is_quarter_panel = any(t in orig for t in {
        "quarter panel", "door panel", "door", "sill", "rocker", "fender",
        "wing", "arch", "wheel arch", "wheel well",
    })
    orig_is_glass  = any(t in orig for t in {"window", "glass", "windscreen", "windshield"})
    orig_is_wiper  = "wiper" in orig
    orig_is_handle = any(t in orig for t in {"handle", "handle cup"})

    ref_is_bumper  = "bumper" in ref
    ref_is_glass   = any(t in ref for t in {"window glass", "windscreen", "windshield"})
    ref_is_wiper   = "wiper" in ref
    ref_is_handle  = any(t in ref for t in {"door handle", "handle cup"})

    # Quarter panel / door / arch CANNOT become bumper — they are different zones.
    # This stops the model mapping "rear quarter panel" → "bumper lip" when
    # the bounding box clips the bumper edge.
    if orig_is_quarter_panel and not orig_is_bumper and ref_is_bumper:
        return False

    # Body panels should not become glass
    if not orig_is_glass and ref_is_glass:
        return False

    # Body panels should not become wipers
    if not orig_is_wiper and ref_is_wiper:
        return False

    # Body panels should not become door handles
    if not orig_is_handle and ref_is_handle:
        return False

    # Glass locations should not become body-panel components
    if orig_is_glass and not ref_is_glass and not ref_is_wiper:
        # Exception: seals around glass are fine
        if not any(t in ref for t in {"seal", "weatherstrip", "rubber", "trim"}):
            return False

    return True
