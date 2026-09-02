"""
Integration test — runs the full audit + comparison pipeline end-to-end.
Requires the real video and Claude API.

Run with:
    pytest tests/integration/ -m integration -v -s
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]


VIDEO_PATH  = Path(__file__).parent.parent.parent / "data/input/videos/car_rental_video.mp4"
COMPANY_PDF = Path(__file__).parent.parent.parent / "data/input/company_reports/rental_company_report.pdf"


@pytest.fixture(scope="module", autouse=True)
def require_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")


@pytest.fixture(scope="module", autouse=True)
def require_video():
    if not VIDEO_PATH.exists():
        pytest.skip(f"Video not found: {VIDEO_PATH}")


def test_audit_pipeline_produces_session(tmp_path):
    """run_audit returns a session with damages and a PDF."""
    from rentalshield.pipeline import run_audit

    session = run_audit(
        video_path       = VIDEO_PATH,
        output_dir       = tmp_path,
        frame_interval_s = 10.0,   # fast for test
    )

    assert session.session_id
    assert session.video_path == VIDEO_PATH
    assert session.audit_pdf and session.audit_pdf.exists()
    # Damages may be 0 (clean car) but the session itself must be valid
    assert isinstance(session.damages, list)


def test_comparison_pipeline_produces_report(tmp_path):
    """run_comparison returns a report PDF when company PDF exists."""
    if not COMPANY_PDF.exists():
        pytest.skip(f"Company PDF not found: {COMPANY_PDF}")

    from rentalshield.pipeline import run_audit, run_comparison

    audit = run_audit(
        video_path       = VIDEO_PATH,
        output_dir       = tmp_path / "audit",
        frame_interval_s = 10.0,
    )
    comp = run_comparison(
        audit_session = audit,
        company_pdf   = COMPANY_PDF,
        output_dir    = tmp_path / "compare",
    )

    assert comp.report_pdf and comp.report_pdf.exists()
    assert isinstance(comp.company_damages, list)
    assert isinstance(comp.comparison, list)


def test_json_roundtrip(tmp_path):
    """Damage JSON saved by audit can be loaded and used by compare."""
    from rentalshield.pipeline import run_audit, run_comparison

    audit = run_audit(
        video_path       = VIDEO_PATH,
        output_dir       = tmp_path,
        frame_interval_s = 15.0,
    )

    json_path = tmp_path / audit.session_id / "damages.json"
    assert json_path.exists()

    if COMPANY_PDF.exists():
        comp = run_comparison(
            damages_json = json_path,
            company_pdf  = COMPANY_PDF,
            output_dir   = tmp_path,
        )
        assert comp.report_pdf and comp.report_pdf.exists()
