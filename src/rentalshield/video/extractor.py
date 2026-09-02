"""
Video frame extraction.
Pulls one representative frame every N seconds for analysis.
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import cv2
from loguru import logger


# Seconds between the MP4/QuickTime epoch (1904-01-01) and Unix epoch (1970-01-01)
_MP4_EPOCH_OFFSET = int((datetime(1970, 1, 1) - datetime(1904, 1, 1)).total_seconds())


def get_gps_from_video(video_path: Path) -> tuple[float, float] | None:
    """
    Extract GPS coordinates embedded by the phone camera in the MP4 file.

    iPhones write coordinates in a '©xyz' (0xa9 'xyz') atom as an ISO-6709 string,
    e.g. "+41.3851+002.1734+017.000/" (lat, lon, alt).
    Android uses the same atom or a 'loci' atom.

    Returns (latitude, longitude) or None if not present / location was off.

    To enable GPS embedding:
      iPhone  → Settings → Privacy → Location Services → Camera → While Using
      Android → Camera app → Settings → Save location → ON
    """
    import re as _re
    try:
        with open(video_path, "rb") as f:
            data = f.read()

        # ©xyz atom: byte 0xa9 followed by 'xyz'
        idx = data.find(b"\xa9xyz")
        if idx >= 0:
            # Atom layout: 4-byte size | 4-byte name | 2-byte data-len | 2-byte locale | string
            body = data[idx + 4:]
            str_len  = struct.unpack(">H", body[0:2])[0]
            coord_str = body[4 : 4 + str_len].decode("utf-8", errors="replace").strip()
            # ISO-6709: "+41.3851+002.1734+017.000/"
            m = _re.match(r"([+-]\d+\.\d+)([+-]\d+\.\d+)", coord_str)
            if m:
                lat = float(m.group(1))
                lon = float(m.group(2))
                logger.info("GPS from video: {:.5f}, {:.5f}", lat, lon)
                return lat, lon

        # Fallback: scan for ISO-6709 pattern anywhere in the file
        text = data.decode("latin-1", errors="replace")
        matches = _re.findall(r"([+-]\d{2,3}\.\d{4,6})([+-]\d{2,3}\.\d{4,6})/", text)
        if matches:
            lat, lon = float(matches[0][0]), float(matches[0][1])
            logger.info("GPS from video (scan): {:.5f}, {:.5f}", lat, lon)
            return lat, lon

        return None

    except Exception as exc:
        logger.debug("Could not read GPS from {}: {}", video_path.name, exc)
        return None


def get_recording_time(video_path: Path) -> datetime | None:
    """
    Return the timestamp when the video was RECORDED (from the MP4 mvhd atom),
    or None if it cannot be determined.

    Phone cameras embed the recording time in the MP4 container's 'mvhd' atom.
    This is the correct inspection time to show on the report — not datetime.now().
    """
    try:
        with open(video_path, "rb") as f:
            content = f.read()

        idx = content.find(b"mvhd")
        if idx < 0:
            return None

        # mvhd atom structure (version 0):
        #   4 bytes size | 4 bytes 'mvhd' | 1 byte version | 3 bytes flags
        #   | 4 bytes creation_time | 4 bytes modification_time | ...
        # Body starts right after the 'mvhd' 4-byte tag (idx+4).
        body   = content[idx + 4:]
        version = body[0]
        if version == 0:
            ct = struct.unpack(">I", body[4:8])[0]   # 32-bit seconds
        else:
            ct = struct.unpack(">Q", body[4:12])[0]  # 64-bit seconds

        unix_ts = ct - _MP4_EPOCH_OFFSET
        if unix_ts <= 0:
            return None

        return datetime.fromtimestamp(unix_ts, tz=timezone.utc).astimezone()

    except Exception as exc:
        logger.debug("Could not read recording time from {}: {}", video_path.name, exc)
        return None


class VideoExtractor:
    """
    Extracts frames from a video file at a configurable interval.

    Usage:
        extractor = VideoExtractor("car_rental_video.mp4", interval_s=2)
        for frame_no, time_sec, frame in extractor.frames():
            ...
    """

    def __init__(self, video_path: str | Path, interval_s: float = 2.0):
        self.video_path  = Path(video_path)
        self.interval_s  = interval_s

        if not self.video_path.exists():
            raise FileNotFoundError(f"Video not found: {self.video_path}")

        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            raise IOError(f"Cannot open video: {self.video_path}")

        self.fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration_s   = self.total_frames / self.fps
        cap.release()

        self._interval_frames = max(1, int(self.fps * self.interval_s))

        logger.info(
            "Video: {}  |  {:.0f}s  |  {:.0f} fps  |  "
            "Sampling every {:.1f}s  (~{} frames to analyze)",
            self.video_path.name,
            self.duration_s,
            self.fps,
            self.interval_s,
            self.sample_count,
        )

    @property
    def sample_count(self) -> int:
        """Number of frames that will be analyzed."""
        return max(1, int(self.duration_s / self.interval_s))

    def frames(self) -> Generator[tuple[int, float, "cv2.Mat"], None, None]:
        """
        Yield (frame_number, time_sec, frame) for each sample frame.
        Frame numbers are 1-based.
        """
        cap       = cv2.VideoCapture(str(self.video_path))
        frame_no  = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame_no += 1
                if frame_no % self._interval_frames == 0:
                    time_sec = round(frame_no / self.fps, 2)
                    yield frame_no, time_sec, frame
        finally:
            cap.release()

    def extract_at(self, time_sec: float) -> "cv2.Mat | None":
        """Extract a single frame at a specific timestamp (for tests / fixtures)."""
        cap = cv2.VideoCapture(str(self.video_path))
        frame_no = int(time_sec * self.fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = cap.read()
        cap.release()
        return frame if ret else None

    def save_fixture_frames(
        self,
        output_dir: Path,
        timestamps: list[float],
    ) -> list[Path]:
        """
        Save specific frames as JPEG files (used to create test fixtures).
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for ts in timestamps:
            frame = self.extract_at(ts)
            if frame is None:
                logger.warning("Could not extract frame at {}s", ts)
                continue
            path = output_dir / f"frame_{ts:.1f}s.jpg"
            cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            paths.append(path)
            logger.debug("Saved fixture frame: {}", path.name)
        return paths
