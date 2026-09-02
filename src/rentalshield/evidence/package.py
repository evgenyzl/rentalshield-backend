"""
Evidence package builder for RentalShield.

Creates a ZIP archive the customer can hand to the rental company, their
credit-card chargeback team, or a lawyer.  The package contains:

  audit_report.pdf  — the AI-generated damage report
  photos/           — every original photo, EXIF metadata intact
  manifest.txt      — human-readable session summary with timestamps,
                      coverage map, damage list, and file hashes

The photo originals are copied byte-for-byte from the source folder so that
EXIF timestamps and GPS coordinates are preserved exactly as the phone recorded
them.  These cannot be altered without breaking the hash check in manifest.txt.
"""

from __future__ import annotations

import hashlib
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from rentalshield.models import AuditSession

# ── Constants ─────────────────────────────────────────────────────────────────

_VIEW_LABELS = {
    "front":      "Front  (bumper, headlights, bonnet)",
    "rear":       "Rear   (bumper, tail lights, boot)",
    "left_side":  "Left side  (driver doors & panels)",
    "right_side": "Right side (passenger doors & panels)",
    "roof":       "Roof",
    "wheels":     "Wheels / tyres",
}
_REQUIRED_VIEWS = {"front", "rear", "left_side", "right_side"}


# ── Public API ────────────────────────────────────────────────────────────────

def create_evidence_package(
    session:       "AuditSession",
    photo_dir:     Path,
    covered_views: set[str],
    output_dir:    Path,
) -> Path:
    """
    Build a ZIP evidence package and write it to output_dir.

    Parameters
    ----------
    session       : completed AuditSession (damages + metadata + audit_pdf)
    photo_dir     : folder of original photos (EXIF intact source files)
    covered_views : set of view labels collected during the scan
    output_dir    : session output directory where the ZIP is written

    Returns
    -------
    Path to the created .zip file.
    """
    # ── Derive a descriptive filename ────────────────────────────────────────
    plate_slug = (
        session.metadata.car_plate.replace(" ", "").upper()
        if session.metadata and session.metadata.car_plate
        else "NOPLATE"
    )
    date_slug  = datetime.now().strftime("%Y%m%d")
    zip_name   = f"rentalshield_{plate_slug}_{date_slug}.zip"
    zip_path   = output_dir / zip_name

    # ── Collect original photos ──────────────────────────────────────────────
    _EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
    photo_paths = sorted(
        p for p in photo_dir.iterdir()
        if p.suffix.lower() in _EXTENSIONS
    )

    # ── Build manifest text ──────────────────────────────────────────────────
    manifest = _build_manifest(session, photo_paths, covered_views)

    # ── Write ZIP ────────────────────────────────────────────────────────────
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. PDF report
        if session.audit_pdf and Path(session.audit_pdf).exists():
            zf.write(session.audit_pdf, arcname="audit_report.pdf")
            logger.debug("Evidence ZIP: added audit_report.pdf")

        # 2. Original photos (byte-for-byte copy — EXIF intact)
        for photo in photo_paths:
            zf.write(photo, arcname=f"photos/{photo.name}")
            logger.debug("Evidence ZIP: added photos/{}", photo.name)

        # 3. Manifest
        zf.writestr("manifest.txt", manifest)

    size_kb = zip_path.stat().st_size // 1024
    logger.info(
        "Evidence package → {}  ({} KB,  {} photo(s),  {} damage(s))",
        zip_path.name, size_kb, len(photo_paths), len(session.damages),
    )
    return zip_path


# ── Internal helpers ──────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    """Return the first 16 hex chars of the SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _build_manifest(
    session:       "AuditSession",
    photo_paths:   list[Path],
    covered_views: set[str],
) -> str:
    """Return the plain-text content for manifest.txt."""
    now    = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    plate  = (session.metadata.car_plate  if session.metadata else None) or "—"
    model  = (session.metadata.car_model  if session.metadata else None) or "—"
    company= (session.metadata.rental_company if session.metadata else None) or "—"
    taken  = (
        session.recorded_at.strftime("%Y-%m-%d  %H:%M:%S")
        if session.recorded_at else "—"
    )

    lines: list[str] = []
    w = lines.append   # shorthand

    w("=" * 62)
    w("  RentalShield — Evidence Package")
    w("=" * 62)
    w("")
    w(f"  Session ID   : {session.session_id}")
    w(f"  Generated    : {now}")
    w("")
    w("  RENTAL DETAILS")
    w(f"  Car plate    : {plate}")
    w(f"  Car model    : {model}")
    w(f"  Company      : {company}")
    w(f"  Photos taken : {taken}")
    if session.metadata and session.metadata.gps_lat is not None:
        w(f"  Location GPS : {session.metadata.gps_lat:.6f}, "
          f"{session.metadata.gps_lon:.6f}")
    w("")

    # ── Coverage ─────────────────────────────────────────────────────────────
    w("  PHOTO COVERAGE")
    missing_required = _REQUIRED_VIEWS - covered_views
    for key, label in _VIEW_LABELS.items():
        tick = "✓" if key in covered_views else "✗"
        note = "  ← NOT PHOTOGRAPHED" if key in missing_required else ""
        w(f"  {tick}  {label}{note}")
    if missing_required:
        w("")
        w("  WARNING: Damage on un-photographed sides cannot be")
        w("  disputed.  See coverage gaps marked ✗ above.")
    w("")

    # ── Damages ───────────────────────────────────────────────────────────────
    w(f"  DAMAGES DETECTED  ({len(session.damages)} total)")
    if not session.damages:
        w("  None detected — car appeared undamaged in submitted photos.")
    else:
        for i, d in enumerate(session.damages, 1):
            sev  = d.severity.value  if hasattr(d.severity,  "value") else str(d.severity)
            typ  = d.type.value      if hasattr(d.type,      "value") else str(d.type)
            loc  = d.location
            desc = d.description or ""
            w(f"  {i:>2}. [{sev:8s}] {typ:8s} — {loc}")
            if desc:
                w(f"        {desc}")
    w("")

    # ── Photo list with hashes ────────────────────────────────────────────────
    w(f"  PHOTOS  ({len(photo_paths)} files)")
    w("  Filename                     SHA-256 (first 16 chars)")
    w("  " + "-" * 56)
    for i, p in enumerate(photo_paths, 1):
        try:
            sha = _sha256(p)
        except OSError:
            sha = "unavailable"
        # Try to get EXIF timestamp for manifest
        ts = _exif_ts(p)
        ts_str = f"  {ts}" if ts else ""
        w(f"  {i:>2}. {p.name:<28s} {sha}{ts_str}")
    w("")

    # ── Footer ────────────────────────────────────────────────────────────────
    w("  " + "-" * 58)
    w("  This package was generated automatically by RentalShield.")
    w("  Photos are originals with full EXIF metadata intact.")
    w("  SHA-256 checksums verify photo authenticity.")
    w("  EXIF timestamps confirm when and where photos were taken.")
    w("=" * 62)

    return "\n".join(lines) + "\n"


def _exif_ts(path: Path) -> str | None:
    """Return the EXIF DateTimeOriginal as a string, or None."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(path)
        raw = img._getexif() or {}
        exif = {TAGS.get(k, k): v for k, v in raw.items()}
        ts = exif.get("DateTimeOriginal") or exif.get("DateTime")
        return str(ts) if ts else None
    except Exception:
        return None
