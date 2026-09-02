"""
Unit tests for VideoExtractor — no API calls, uses the real video file if present.
"""

from __future__ import annotations

import pytest

from rentalshield.video.extractor import VideoExtractor

VIDEO_PATH = pytest.importorskip  # handled below


class TestVideoExtractor:
    @pytest.fixture
    def video_path(self):
        from pathlib import Path
        p = Path(__file__).parent.parent.parent / "data/input/videos/car_rental_video.mp4"
        if not p.exists():
            pytest.skip(f"Video not found: {p}")
        return p

    def test_opens_valid_video(self, video_path):
        ext = VideoExtractor(video_path, interval_s=5.0)
        assert ext.fps > 0
        assert ext.duration_s > 0
        assert ext.total_frames > 0

    def test_raises_for_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            VideoExtractor(tmp_path / "nonexistent.mp4")

    def test_sample_count_sensible(self, video_path):
        ext = VideoExtractor(video_path, interval_s=5.0)
        expected = int(ext.duration_s / 5.0)
        # Allow ±1 for rounding
        assert abs(ext.sample_count - expected) <= 1

    def test_frames_generator_yields_frames(self, video_path):
        """Generator yields at least one (frame_no, time_sec, frame) tuple."""
        import numpy as np
        ext = VideoExtractor(video_path, interval_s=10.0)
        frames = list(ext.frames())
        assert len(frames) >= 1
        frame_no, time_sec, frame = frames[0]
        assert frame_no > 0
        assert time_sec >= 0
        assert isinstance(frame, np.ndarray)
        assert frame.shape[2] == 3   # BGR

    def test_extract_at_returns_frame(self, video_path):
        ext = VideoExtractor(video_path, interval_s=5.0)
        frame = ext.extract_at(2.0)
        assert frame is not None
        assert frame.shape[2] == 3

    def test_extract_at_beyond_duration_returns_none(self, video_path):
        ext = VideoExtractor(video_path, interval_s=5.0)
        frame = ext.extract_at(99999.0)
        assert frame is None

    def test_save_fixture_frames(self, video_path, tmp_path):
        ext = VideoExtractor(video_path, interval_s=5.0)
        paths = ext.save_fixture_frames(tmp_path, timestamps=[2.0, 5.0])
        assert len(paths) >= 1
        for p in paths:
            assert p.exists()
            assert p.stat().st_size > 0
