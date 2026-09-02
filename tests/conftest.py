"""
Shared pytest fixtures for all test suites.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from rentalshield.models import Damage, DamageType, Severity, BoundingBox


# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
FRAMES_DIR   = FIXTURES_DIR / "frames"
VIDEO_PATH   = PROJECT_ROOT / "data" / "input" / "videos" / "car_rental_video.mp4"
COMPANY_PDF  = PROJECT_ROOT / "data" / "input" / "company_reports" / "rental_company_report.pdf"


# ── Fixture frames ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fixture_frames_dir() -> Path:
    """Extract and cache test frames from the video (runs once per test session)."""
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    # Check if frames already exist
    existing = list(FRAMES_DIR.glob("frame_*.jpg"))
    if existing:
        return FRAMES_DIR

    # Extract frames only if the video exists
    if not VIDEO_PATH.exists():
        pytest.skip(f"Video not found: {VIDEO_PATH}")

    cap = cv2.VideoCapture(str(VIDEO_PATH))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total / fps

    # Pick 3 frames spread across the video
    timestamps = [
        max(2.0, duration * 0.15),
        duration * 0.50,
        max(0, duration * 0.85),
    ]

    for ts in timestamps:
        frame_no = int(ts * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = cap.read()
        if ret:
            path = FRAMES_DIR / f"frame_{ts:.1f}s.jpg"
            cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

    cap.release()
    return FRAMES_DIR


@pytest.fixture(scope="session")
def sample_frame_paths(fixture_frames_dir) -> list[Path]:
    """Return paths to the saved test frames."""
    return sorted(fixture_frames_dir.glob("frame_*.jpg"))


# ── Synthetic frames ───────────────────────────────────────────────────────────

@pytest.fixture
def blank_frame() -> "np.ndarray":
    """A plain grey frame — no car, no damage. Claude should return []."""
    return np.full((480, 640, 3), 128, dtype=np.uint8)


@pytest.fixture
def red_noise_frame() -> "np.ndarray":
    """Random noise — should not produce high-confidence damages."""
    rng = np.random.default_rng(42)
    return rng.integers(0, 256, (480, 640, 3), dtype=np.uint8)


# ── Sample damage objects ──────────────────────────────────────────────────────

@pytest.fixture
def sample_damage() -> Damage:
    return Damage(
        type        = DamageType.SCRATCH,
        location    = "front left door",
        severity    = Severity.MINOR,
        description = "A thin scratch along the lower edge of the door panel.",
        time_sec    = 12.5,
        frame       = 375,
        bbox        = BoundingBox(x_pct=0.2, y_pct=0.6, w_pct=0.15, h_pct=0.05),
    )


@pytest.fixture
def sample_damages() -> list[Damage]:
    return [
        Damage(
            type="SCRATCH", location="front left door",
            severity="MINOR",
            description="Thin scratch along lower edge.",
        ),
        Damage(
            type="DENT", location="rear right fender",
            severity="MODERATE",
            description="Small dent near wheel arch.",
        ),
        Damage(
            type="CHIP", location="front bumper center",
            severity="MINOR",
            description="Paint chip, about 1cm diameter.",
        ),
    ]


@pytest.fixture
def sample_company_damages() -> list[dict]:
    return [
        {"type": "SCRATCH", "location": "front left door",
         "severity": "MINOR",  "notes": "minor scratch LF door lower edge"},
        {"type": "CHIP",    "location": "front bumper",
         "severity": "MINOR",  "notes": "stone chip front bumper"},
    ]
