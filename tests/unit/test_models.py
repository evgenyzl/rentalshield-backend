"""
Unit tests for data models — no API calls, no files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rentalshield.models import (
    Damage, DamageType, Severity, BoundingBox,
    AuditSession, ComparisonItem, ComparisonStatus,
)
from datetime import datetime


class TestDamage:
    def test_round_trip_json(self, sample_damage):
        """Damage survives serialize → deserialize unchanged."""
        d = sample_damage
        exported = d.to_export_dict()
        restored = Damage.from_dict(exported)

        assert restored.type     == d.type
        assert restored.location == d.location
        assert restored.severity == d.severity
        assert restored.time_sec == d.time_sec

    def test_from_dict_defaults(self):
        """from_dict works with minimal keys."""
        d = Damage.from_dict({
            "type": "DENT",
            "location": "rear bumper",
            "severity": "MODERATE",
            "description": "Small dent.",
        })
        assert d.type     == DamageType.DENT
        assert d.frame    is None
        assert d.img_path is None

    def test_bounding_box_clamped(self):
        """BoundingBox values are validated to 0–1."""
        with pytest.raises(Exception):
            BoundingBox(x_pct=1.5, y_pct=0.0, w_pct=0.2, h_pct=0.2)

    def test_export_img_path_string(self, sample_damage):
        """img_path is serialised as a string, not a Path object."""
        sample_damage.img_path = Path("/tmp/test.jpg")
        exported = sample_damage.to_export_dict()
        assert isinstance(exported["img_path"], str)

    def test_export_no_img_path(self, sample_damage):
        """img_path=None is preserved as None in export."""
        sample_damage.img_path = None
        exported = sample_damage.to_export_dict()
        assert exported["img_path"] is None


class TestAuditSession:
    def test_new_damage_count(self, sample_damages):
        session = AuditSession(
            session_id="test_001",
            video_path=Path("/tmp/video.mp4"),
            created_at=datetime.now(),
            damages=sample_damages,
        )
        assert session.new_damage_count == 3

    def test_empty_session(self):
        session = AuditSession(
            session_id="empty",
            video_path=Path("/tmp/video.mp4"),
            created_at=datetime.now(),
        )
        assert session.new_damage_count == 0
        assert session.damages == []


class TestComparisonStatus:
    def test_new_damages_filter(self):
        from rentalshield.models import ComparisonSession

        items = [
            ComparisonItem(
                my_index=0, my_location="front door",
                my_type=DamageType.SCRATCH, my_description="scratch",
                status=ComparisonStatus.NEW, reason="not in company list",
            ),
            ComparisonItem(
                my_index=1, my_location="rear bumper",
                my_type=DamageType.DENT, my_description="dent",
                status=ComparisonStatus.MATCHED, reason="documented",
            ),
        ]
        session = ComparisonSession(
            session_id="cmp_001",
            audit_session_id="aud_001",
            company_pdf=Path("/tmp/report.pdf"),
            created_at=datetime.now(),
            comparison=items,
        )
        assert len(session.new_damages)     == 1
        assert len(session.matched_damages) == 1
        assert session.new_damages[0].my_location == "front door"
