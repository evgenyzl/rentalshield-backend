"""
Automatic licence plate reader.

Extracts 3 frames from the start of the video and asks the AI to
read the plate number.  Works with any BaseAnalyzer (Gemini or Claude).
Returns None when the plate is not legible.
"""

from __future__ import annotations

import cv2
from loguru import logger

from rentalshield.ai.base import BaseAnalyzer


_PLATE_PROMPT = """\
Look at this photo of a car.
Find the licence plate (number plate) and return ONLY the plate text exactly as it appears, \
including spaces or dashes (e.g. "ABC-1234", "B 7823 CK", "6KXH320").
If the plate is not visible, not readable, or you are not confident, reply with exactly: NOT_VISIBLE
Reply with nothing else — no punctuation, no explanation."""


def detect_plate_from_photos(photo_paths: list, analyzer: BaseAnalyzer) -> str | None:
    """
    Try to read the licence plate from a list of photo frames (cv2 arrays or paths).
    Scans all photos and returns the most common legible result, or None.
    """
    from collections import Counter
    from pathlib import Path

    candidates: list[str] = []

    for item in photo_paths:
        # Stop after 3 candidates — enough to confirm the plate reliably
        if len(candidates) >= 3:
            break

        # Accept either a cv2 frame (ndarray) or a file path
        if isinstance(item, (str, Path)):
            frame = cv2.imread(str(item))
            if frame is None:
                continue
        else:
            frame = item  # already a cv2 Mat

        try:
            # Short 15s timeout — if the server is busy we skip to the next photo
            raw = analyzer.generate_text_with_image(frame, _PLATE_PROMPT, timeout=15.0)
        except AttributeError:
            logger.debug("plate_detector: provider does not support image+text, skipping")
            break
        except Exception as exc:
            logger.warning("plate_detector: error on photo — {}", exc)
            continue

        raw = raw.strip().upper()
        if raw and raw != "NOT_VISIBLE" and len(raw) >= 4:
            candidates.append(raw)
            logger.info("plate_detector: candidate → {}", raw)
        else:
            logger.debug("plate_detector: plate not visible in photo")

    if not candidates:
        return None

    plate = Counter(candidates).most_common(1)[0][0]
    logger.info("plate_detector: plate = {}", plate)
    return plate


def detect_plate(video_path: "Path", analyzer: BaseAnalyzer) -> str | None:
    """
    Try to read the licence plate from the first few seconds of the video.

    Returns the plate string (e.g. "B-7823-CK") or None if not found.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning("plate_detector: cannot open {}", video_path)
        return None

    fps      = cap.get(cv2.CAP_PROP_FPS) or 30
    duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps

    # Sample at 2s, 5s, 8s (or shorter if video is brief)
    sample_times = [t for t in [2.0, 5.0, 8.0] if t < duration]
    if not sample_times:
        sample_times = [0.5]

    candidates: list[str] = []

    for t in sample_times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue

        try:
            raw = analyzer.generate_text_with_image(frame, _PLATE_PROMPT)
        except AttributeError:
            # Fallback: generate_text can't do images on all backends.
            # Use analyze_frame indirectly — skip if not supported.
            logger.debug("plate_detector: provider does not support image+text, skipping")
            break
        except Exception as exc:
            logger.warning("plate_detector: error at {:.1f}s — {}", t, exc)
            continue

        raw = raw.strip().upper()
        if raw and raw != "NOT_VISIBLE" and len(raw) >= 4:
            candidates.append(raw)
            logger.info("plate_detector: candidate at {:.1f}s → {}", t, raw)
        else:
            logger.debug("plate_detector: not visible at {:.1f}s", t)

    cap.release()

    if not candidates:
        return None

    # Return the most common candidate (in case multiple frames agree)
    from collections import Counter
    plate = Counter(candidates).most_common(1)[0][0]
    logger.info("plate_detector: plate = {}", plate)
    return plate
