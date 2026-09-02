"""
Image utilities — saving damage evidence images.

Two images are saved per detected damage:
  1. Full annotated frame  (f{n}_full_{type}_{slug}.jpg)
     The complete video frame with a red rectangle + label marking the damage.
     This is the LEGAL EVIDENCE — it shows the full car context and exact location.

  2. Crop  (f{n}_{type}_{slug}.jpg)
     A tight crop around the damage area, used in the report's photo column for
     quick visual reference.

The full frame is what a dispute arbiter, insurance company, or court would rely on.
The crop is just a thumbnail.
"""

from __future__ import annotations

from pathlib import Path

import cv2

from rentalshield.models import Damage

# Red rectangle colour (BGR)
_RED   = (0,   0,   255)
_WHITE = (255, 255, 255)
_BLACK = (0,   0,   0)


def save_damage_images(
    frame:    "cv2.Mat",
    damage:   Damage,
    out_dir:  Path,
    frame_no: int,
) -> tuple[Path, Path]:
    """
    Save two images for one detected damage and return (full_path, crop_path).

    full_path : annotated full frame — primary legal evidence
    crop_path : tight crop with red box — used as thumbnail in PDF report
    """
    h, w = frame.shape[:2]
    bbox = damage.bbox

    # Bounding box in pixels
    x  = int((bbox.x_pct if bbox else 0.1) * w)
    y  = int((bbox.y_pct if bbox else 0.1) * h)
    bw = int((bbox.w_pct if bbox else 0.2) * w)
    bh = int((bbox.h_pct if bbox else 0.2) * h)

    # Clamp to frame bounds
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(w, x + bw), min(h, y + bh)

    slug = damage.location.lower().replace(" ", "_")[:30]
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"f{frame_no:05d}_{damage.type.value}_{slug}"

    # ── 1. Full annotated frame ───────────────────────────────────────────────
    full = frame.copy()
    thickness = max(3, w // 200)   # scale line width to frame size

    # Red rectangle around damage
    cv2.rectangle(full, (x1, y1), (x2, y2), _RED, thickness)

    # Label above the box: "SCRATCH — rear passenger door"
    label = f"{damage.type.value} — {damage.location[:40]}"
    font       = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = max(0.5, w / 2000)
    (tw, th), baseline = cv2.getTextSize(label, font, font_scale, 2)
    lx = max(0, x1)
    ly = max(th + 6, y1 - 8)
    # Background pill for readability
    cv2.rectangle(full, (lx - 2, ly - th - 4), (lx + tw + 4, ly + baseline), _RED, -1)
    cv2.putText(full, label, (lx, ly), font, font_scale, _WHITE, 2, cv2.LINE_AA)

    # Downscale very tall portrait frames to ≤ 1080px height for the PDF
    max_h = 1080
    if h > max_h:
        scale = max_h / h
        full  = cv2.resize(full, (int(w * scale), max_h))

    full_path = out_dir / f"{base}_full.jpg"
    cv2.imwrite(str(full_path), full, [cv2.IMWRITE_JPEG_QUALITY, 90])

    # ── 2. Crop thumbnail ─────────────────────────────────────────────────────
    pad  = 40
    cx1  = max(0, x1 - pad)
    cy1  = max(0, y1 - pad)
    cx2  = min(w, x2 + pad)
    cy2  = min(h, y2 + pad)

    crop_frame = frame.copy()
    cv2.rectangle(crop_frame, (x1, y1), (x2, y2), _RED, thickness)
    crop = crop_frame[cy1:cy2, cx1:cx2]

    crop_path = out_dir / f"{base}.jpg"
    cv2.imwrite(str(crop_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 88])

    return full_path, crop_path


# ── Backward-compat shim (old name used in tests / older pipeline code) ───────
def save_damage_crop(
    frame:    "cv2.Mat",
    damage:   Damage,
    out_dir:  Path,
    frame_no: int,
    padding:  int = 30,
) -> Path:
    """Legacy wrapper — returns only the crop path."""
    _, crop_path = save_damage_images(frame, damage, out_dir, frame_no)
    return crop_path
