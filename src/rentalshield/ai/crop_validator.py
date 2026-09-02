"""
Crop validation — second-pass check on each detected damage.

After the main scan, every saved crop image is shown to the AI with a
simple binary question: "is this actually a car body panel with real damage?"

This catches false positives that slip through:
  • Frames showing trees, ground, people, background vehicles
  • Very dark or blurry frames the edge-density filter missed
  • Frames where the AI hallucinated a scuff on non-car content

Cost: ~50 tokens per crop (tiny image + yes/no prompt).
With 14 crops that's ~700 tokens total — negligible.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import cv2
from loguru import logger

_VALIDATE_PROMPT = """\
This crop was flagged by another AI as damage on a car. Confirm or reject it.

Answer with ONLY the single word YES or NO — nothing else.

Answer YES if this crop shows a car exterior panel and there is ANY plausible
sign of damage — scratch, dent, chip, crack, scuff, paint transfer, curb rash,
missing/torn part, or paint break. Bumper marks, plastic trim scuffs, and
faint scratches on painted metal ALL count as YES.

Trust the previous AI unless the crop is CLEARLY one of:
  • A pure sky, road, tree, or building scene with no car surface visible
  • Car interior (dashboard, seat, steering wheel)
  • A completely black or overexposed frame with nothing visible
  • Obviously just water droplets or a wet gleam with no mark beneath

When there is any doubt at all whether the crop shows a real mark on paint or
plastic → answer YES. Missing a real damage is far worse than accepting a
subtle one. This is a confirmation step, not a second detection."""

# Minimum gap between crop-validation calls to stay within 15 RPM (= 4s/call).
# Set slightly above 4s so we don't shave the edge.
_MIN_CALL_GAP_S = 5.0


def _parse_retry_delay(exc: Exception) -> float:
    """Extract 'retryDelay' seconds from a Gemini 429 error string, default 60."""
    text = str(exc)
    m = re.search(r"retryDelay.*?(\d+)s", text)
    if m:
        return float(m.group(1)) + 2   # add a small buffer
    return 60.0


def validate_crop(img_path: Path, analyzer, _last_call: list | None = None) -> bool:
    """
    Return True if the crop image shows a real car panel with real damage.
    Return False → the detection is a false positive and should be dropped.

    _last_call is a mutable one-element list used to track the timestamp of
    the previous call so we can space calls ≥ _MIN_CALL_GAP_S apart.
    Pass the same list across all calls in a validation loop.
    """
    if _last_call is None:
        _last_call = [0.0]

    frame = cv2.imread(str(img_path))
    if frame is None:
        logger.warning("Crop validator: cannot read {}", img_path)
        return True   # don't drop if we can't read the file

    # ── Rate pacing: enforce minimum gap between calls ────────────────────────
    gap = time.time() - _last_call[0]
    if gap < _MIN_CALL_GAP_S:
        wait = _MIN_CALL_GAP_S - gap
        logger.debug("Crop validator: spacing {:.1f}s before next call …", wait)
        time.sleep(wait)

    # ── Call with one 429-retry ───────────────────────────────────────────────
    for attempt in range(2):
        try:
            _last_call[0] = time.time()
            raw = analyzer.generate_text_with_image(frame, _VALIDATE_PROMPT)
            answer = raw.strip().upper()
            is_valid = answer.startswith("YES")
            if not is_valid:
                logger.info(
                    "Crop rejected by validator: {}  (answer: {!r})",
                    img_path.name, raw.strip()[:40],
                )
            else:
                logger.debug(
                    "Crop confirmed: {}  (answer: {!r})",
                    img_path.name, raw.strip()[:40],
                )
            return is_valid

        except Exception as exc:
            err = str(exc)
            if ("429" in err or "RESOURCE_EXHAUSTED" in err) and attempt == 0:
                wait = _parse_retry_delay(exc)
                logger.warning(
                    "Crop validator: rate-limited on {} — waiting {:.0f}s …",
                    img_path.name, wait,
                )
                time.sleep(wait)
                _last_call[0] = 0.0   # reset gap tracker after long wait
                continue
            # Any other error, or second failure: fail open (keep the damage)
            logger.warning(
                "Crop validator error for {} — keeping damage: {}",
                img_path.name, str(exc)[:120],
            )
            return True

    return True   # should not reach here
