"""
Photo quality assessment and enhancement for RentalShield.

All processing is local (cv2 only) — zero API cost, zero latency overhead.

Two functions exposed to the pipeline:
  assess(frame)          → QualityResult with brightness / blur / verdict
  enhance(frame, result) → enhanced frame (CLAHE + optional sharpen)

CLAHE (Contrast Limited Adaptive Histogram Equalization) works on the
luminance channel in LAB colour space — it boosts local contrast in dark
regions without blowing out highlights and without shifting colours.
Ideal for dim parking garages and dawn/dusk shots.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from loguru import logger


# ── Thresholds ────────────────────────────────────────────────────────────────

# Brightness is the mean pixel value of the greyscale frame (0–255).
_BRIGHT_PITCH_BLACK = 20    # below this: no usable signal even after enhancement
_BRIGHT_DARK        = 60    # below this: enhance before sending to AI
_BRIGHT_OVEREXPOSED = 245   # above this: overexposed (rare outdoors)

# Blur is the variance of the Laplacian — higher = sharper.
_BLUR_UNUSABLE      = 15    # below this: too blurry to assess damage
_BLUR_SOFT          = 60    # below this: warn but still try

# CLAHE parameters
_CLAHE_CLIP  = 3.0          # clip limit — higher = more aggressive boost
_CLAHE_GRID  = (8, 8)       # tile size — smaller = more local contrast


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class QualityResult:
    brightness: float          # mean grey value 0–255
    blur:       float          # Laplacian variance (higher = sharper)
    is_dark:    bool           # needs brightness enhancement
    is_blurry:  bool           # soft / motion-blurred
    is_usable:  bool           # False = skip entirely (pitch black or extreme blur)
    notes:      list[str]      # human-readable issues, e.g. ["dark", "soft"]

    @property
    def label(self) -> str:
        if not self.is_usable:
            return "UNUSABLE"
        if self.notes:
            return f"POOR ({', '.join(self.notes)})"
        return "OK"


# ── Public API ────────────────────────────────────────────────────────────────

def assess(frame: "cv2.Mat") -> QualityResult:
    """
    Measure brightness and sharpness of a frame.
    Runs in < 5 ms — call before every API call.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    brightness = float(gray.mean())
    blur       = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    notes: list[str] = []
    if brightness < _BRIGHT_DARK:
        notes.append("dark")
    if brightness > _BRIGHT_OVEREXPOSED:
        notes.append("overexposed")
    if blur < _BLUR_SOFT:
        notes.append("soft")

    is_usable = brightness >= _BRIGHT_PITCH_BLACK and blur >= _BLUR_UNUSABLE

    return QualityResult(
        brightness = brightness,
        blur       = blur,
        is_dark    = brightness < _BRIGHT_DARK,
        is_blurry  = blur < _BLUR_SOFT,
        is_usable  = is_usable,
        notes      = notes,
    )


def enhance(frame: "cv2.Mat", result: QualityResult) -> "cv2.Mat":
    """
    Enhance the frame for better AI damage detection.
    Only applies processing that is likely to help — does not touch
    already well-lit, sharp photos.

    Returns a new frame (original is not modified).
    """
    out = frame.copy()

    if result.is_dark:
        out = _apply_clahe(out)
        logger.debug(
            "Photo enhancement: CLAHE applied (brightness was {:.0f})",
            result.brightness,
        )

    if result.is_blurry and not result.is_dark:
        # Mild sharpening — skip if we already ran CLAHE (avoids over-processing)
        out = _sharpen(out)
        logger.debug(
            "Photo enhancement: sharpened (blur score was {:.0f})",
            result.blur,
        )

    return out


# ── Internal helpers ──────────────────────────────────────────────────────────

def _apply_clahe(frame: "cv2.Mat") -> "cv2.Mat":
    """
    Apply CLAHE to the L (luminance) channel in LAB colour space.
    Brightens dark areas, preserves colour, avoids global blowout.
    """
    lab        = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b    = cv2.split(lab)
    clahe      = cv2.createCLAHE(clipLimit=_CLAHE_CLIP, tileGridSize=_CLAHE_GRID)
    l_enhanced = clahe.apply(l)
    merged     = cv2.merge([l_enhanced, a, b])
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def _sharpen(frame: "cv2.Mat") -> "cv2.Mat":
    """Mild unsharp-mask to recover detail from slightly soft photos."""
    blur  = cv2.GaussianBlur(frame, (0, 0), 3)
    return cv2.addWeighted(frame, 1.5, blur, -0.5, 0)
