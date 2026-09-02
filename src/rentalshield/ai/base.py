"""
Abstract base class for AI providers.
Both Claude and Gemini implement this interface — the rest of the
pipeline never needs to know which provider is active.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from rentalshield.models import Damage


class BaseAnalyzer(ABC):
    """Common interface for vision-based damage analyzers."""

    @abstractmethod
    def analyze_frame(
        self,
        frame:            "cv2.Mat",
        frame_no:         int   = 0,
        time_sec:         float = 0.0,
        skip_edge_filter: bool  = False,
        is_zone:          bool  = False,
    ) -> list[Damage]:
        """Send a video frame and return detected damages.

        skip_edge_filter: bypass the edge-density pre-filter (set True for photos).
        is_zone: True when the frame is a tight zone crop — uses a more sensitive
                 prompt with a lower confidence threshold (0.55 vs 0.65).
        """
        ...

    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        """Send a text-only prompt and return the raw response string.
        Used by pdf_parser and reconciler."""
        ...

    def is_car(self, frame: "cv2.Mat") -> bool:
        """Cheap pre-flight check: is this photo actually a car?

        Uses a tiny yes/no prompt on a DOWNSCALED image (~512px max side)
        so a 12MP phone shot costs ~1 tile instead of ~200 tiles.
        Gates expensive damage analysis against obviously wrong input
        (screenshots, indoor scenes, selfies). Fail-open on any error.
        """
        try:
            if not hasattr(self, "generate_text_with_image"):
                return True   # can't check → assume yes (fail-open)
            import cv2
            # Downscale to at most 512px on the long side → single tile
            # → ~99% fewer input tokens vs. a full 12MP photo.
            h, w = frame.shape[:2]
            max_side = 512
            if max(h, w) > max_side:
                scale = max_side / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                small_frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            else:
                small_frame = frame
            prompt = (
                "Is the main subject of this image a real car or vehicle exterior "
                "(NOT a screenshot, drawing, indoor scene, person, or object)? "
                "Reply with exactly one word: YES or NO."
            )
            reply = self.generate_text_with_image(small_frame, prompt, timeout=10.0)
            return "yes" in reply.lower()[:20]
        except Exception:
            return True   # on error, fail-open — don't block valid scans
