"""
Photo-based input for RentalShield.

Reads a folder of JPEG/PNG images taken during a guided walkaround
and yields (photo_index, capture_time, cv2_frame) tuples — the same
interface as VideoExtractor, so the rest of the pipeline is unchanged.

Key features:
  • EXIF orientation auto-correction (portrait shots taken sideways)
  • EXIF timestamp extraction (shows real capture time in report)
  • EXIF GPS extraction (if location was enabled on the camera)
  • Downscale to 2048px longest side before sending to AI (saves tokens,
    still 4× sharper than a 1080p video frame)
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Generator

import cv2
import numpy as np
from loguru import logger

try:
    from PIL import Image, ImageOps
    from PIL.ExifTags import TAGS, GPSTAGS
    _PIL_OK = True
except ImportError:
    _PIL_OK = False
    logger.warning("Pillow not installed — EXIF rotation/GPS disabled. pip install Pillow")

# Supported extensions (case-insensitive)
_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

# Max longest dimension sent to AI (tokens ∝ pixels; 2048 is plenty for damage detection)
_MAX_SIDE = 2048


def _load_exif(path: Path) -> dict:
    """Return a flat {tag_name: value} EXIF dict, or {} on failure."""
    if not _PIL_OK:
        return {}
    try:
        img = Image.open(path)
        raw = img._getexif() or {}
        return {TAGS.get(k, k): v for k, v in raw.items()}
    except Exception:
        return {}


def _exif_datetime(exif: dict) -> datetime | None:
    """Parse EXIF DateTimeOriginal → datetime, or None."""
    s = exif.get("DateTimeOriginal") or exif.get("DateTime")
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def _exif_gps(exif: dict) -> tuple[float, float] | None:
    """Extract (lat, lon) from EXIF GPSInfo, or None."""
    if not _PIL_OK:
        return None
    gps_raw = exif.get("GPSInfo", {})
    if not gps_raw:
        return None
    gps = {GPSTAGS.get(k, k): v for k, v in gps_raw.items()}

    def dms(val, ref):
        try:
            d, m, s = float(val[0]), float(val[1]), float(val[2])
            dec = d + m / 60 + s / 3600
            return -dec if ref in ("S", "W") else dec
        except Exception:
            return None

    lat = dms(gps.get("GPSLatitude", ()), gps.get("GPSLatitudeRef", "N"))
    lon = dms(gps.get("GPSLongitude", ()), gps.get("GPSLongitudeRef", "E"))
    if lat is not None and lon is not None:
        return lat, lon
    return None


def _load_frame(path: Path, exif: dict) -> "cv2.Mat":
    """
    Load image as BGR cv2 array, auto-rotate per EXIF orientation,
    and downscale to _MAX_SIDE on the longest side.

    Uses PIL ImageOps.exif_transpose() — the reliable standard for EXIF
    orientation. Avoids the double-rotation bug that occurs when cv2.imread
    auto-applies EXIF on newer OpenCV versions and our code rotates again.
    """
    if _PIL_OK:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img)   # honours orientation tag correctly
        frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    else:
        # PIL not available — fall back to cv2 only (no EXIF correction)
        frame = cv2.imread(str(path))

    if frame is None:
        raise IOError(f"Cannot read image: {path}")

    # Downscale if needed
    h, w = frame.shape[:2]
    longest = max(h, w)
    if longest > _MAX_SIDE:
        scale = _MAX_SIDE / longest
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)),
                           interpolation=cv2.INTER_AREA)

    return frame


class PhotoExtractor:
    """
    Yields (photo_index, capture_datetime_or_None, frame) for each image in a folder.
    Drop-in replacement for VideoExtractor in the pipeline.
    """

    def __init__(self, photo_dir: Path | str):
        self.photo_dir = Path(photo_dir)
        if not self.photo_dir.is_dir():
            raise NotADirectoryError(f"Not a directory: {self.photo_dir}")

        # Skip metadata/reference files (auto-fetched logos, reference car
        # images, generated badges). Convention: those filenames start with '_'
        # to keep them out of the damage-scan loop.
        self.paths = sorted(
            p for p in self.photo_dir.iterdir()
            if p.suffix.lower() in _EXTENSIONS
            and not p.name.startswith("_")
        )
        if not self.paths:
            raise FileNotFoundError(f"No images found in {self.photo_dir}")

        logger.info(
            "Photos: {}  |  {} image(s) to analyze",
            self.photo_dir.name, len(self.paths),
        )

    @property
    def sample_count(self) -> int:
        return len(self.paths)

    def frames(self) -> Generator[tuple[int, datetime | None, "cv2.Mat"], None, None]:
        """Yield (index, capture_time, frame) for each photo."""
        for i, path in enumerate(self.paths, start=1):
            exif    = _load_exif(path)
            cap_at  = _exif_datetime(exif)
            try:
                frame = _load_frame(path, exif)
            except IOError as exc:
                logger.warning("Skipping unreadable photo {}: {}", path.name, exc)
                continue
            logger.debug("Photo {}/{}: {}  ({})", i, len(self.paths), path.name,
                         cap_at.strftime("%H:%M:%S") if cap_at else "no timestamp")
            yield i, cap_at, frame

    def first_frame(self) -> "cv2.Mat | None":
        """Load and return the first photo as a frame. Used by pre-flight checks."""
        if not self.paths:
            return None
        try:
            exif = _load_exif(self.paths[0])
            return _load_frame(self.paths[0], exif)
        except IOError:
            return None

    def get_gps(self) -> tuple[float, float] | None:
        """Return GPS from the first photo that has it, or None."""
        for path in self.paths:
            exif = _load_exif(path)
            gps  = _exif_gps(exif)
            if gps:
                return gps
        return None

    def get_first_capture_time(self) -> datetime | None:
        """Return the timestamp of the first photo."""
        if self.paths:
            return _exif_datetime(_load_exif(self.paths[0]))
        return None
