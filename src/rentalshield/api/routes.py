"""
API endpoints for RentalShield.

POST  /audit              — upload photos, start analysis, return job_id
GET   /audit/{job_id}     — poll status & progress
GET   /audit/{job_id}/report   — download PDF when done
GET   /audit/{job_id}/evidence — download evidence ZIP when done
"""

from __future__ import annotations

import base64
import io
import re
import shutil
import sys
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger

from rentalshield.api.jobs import Job, JobStatus, get_job, new_job
from rentalshield.api.routes.documents import router as documents_router

_UA = "Mozilla/5.0 (compatible; RentalShield/1.0)"

# Wikipedia article titles for company logo lookup
_LOGO_WIKI: dict[str, str] = {
    "hertz":        "The_Hertz_Corporation",
    "sixt":         "Sixt",
    "europcar":     "Europcar",
    "avis":         "Avis_Car_Rental",
    "budget":       "Budget_Rent_a_Car",
    "enterprise":   "Enterprise_Rent-A-Car",
    "national":     "National_Car_Rental",
    "alamo":        "Alamo_Rent_A_Car",
    "dollar":       "Dollar_Rent_A_Car",
    "thrifty":      "Thrifty_Car_Rental",
    "goldcar":      "Goldcar",
    "maggiore":     "Maggiore_rent",
    "noleggiare":   "Noleggiare",
}

def _wiki_thumbnail(wiki_title: str, px: int = 300) -> bytes | None:
    """Fetch a Wikipedia page thumbnail via the REST API. Returns raw image bytes or None."""
    import json
    url = (f"https://en.wikipedia.org/api/rest_v1/page/summary/"
           f"{urllib.parse.quote(wiki_title)}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        # Prefer originalimage, fall back to thumbnail
        src = (data.get("originalimage") or data.get("thumbnail") or {}).get("source", "")
        if not src:
            return None
        # Strip UTM query params that Wikipedia appends (keep the /Npx- size as-is)
        src = re.sub(r'\?.*$', '', src)
        req2 = urllib.request.Request(src, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            return resp2.read()
    except Exception as exc:
        logger.debug("Wikipedia thumbnail fetch failed for '{}': {}", wiki_title, exc)
        return None


def _fetch_logo_server(company: str, out_dir: Path) -> Path | None:
    """Fetch the rental company logo from Wikipedia and save to out_dir.

    Skipped for companies that have a brand-colour badge defined in the report
    generator — those render as a coloured initial badge matching the web UI,
    which is more reliable than Wikipedia's page thumbnails (which often return
    a photo of a building, headquarters, or car instead of the actual logo).
    """
    if not company:
        return None
    # If we have a brand-color badge, use it — cleaner, matches web UI.
    try:
        from rentalshield.report.generator import _COMPANY_COLORS
        if company.lower().strip() in _COMPANY_COLORS:
            logger.info("Using brand badge for '{}' (skipping Wikipedia fetch)", company)
            return None
    except Exception:
        pass
    key = re.sub(r'\b(24[/-]7|rent\s*a\s*car|car\s*rental|mobility|auto|group)\b',
                 '', company, flags=re.I).strip().lower()
    # Match known companies by substring
    wiki_title = None
    for k, title in _LOGO_WIKI.items():
        if k in key:
            wiki_title = title
            break
    if not wiki_title:
        return None
    data = _wiki_thumbnail(wiki_title, px=200)
    if not data:
        return None
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        path = out_dir / "_company_logo.png"
        img.save(str(path), format="PNG")
        logger.info("Logo fetched from Wikipedia for '{}'", company)
        return path
    except Exception as exc:
        logger.warning("Logo save failed: {}", exc)
        return None


def _fetch_car_image_server(car_model: str, out_dir: Path) -> Path | None:
    """Fetch a reference car image from Wikipedia and save to out_dir."""
    if not car_model:
        return None
    CAR_SKIP = {"headquarters","building","factory","office","company","corporation",
                "group","holding","automotive"}
    terms = [car_model.strip(), car_model.strip() + " automobile"]
    for term in terms:
        try:
            import json
            url = (f"https://en.wikipedia.org/api/rest_v1/page/summary/"
                   f"{urllib.parse.quote(term)}")
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            desc = (data.get("description") or "").lower()
            # Skip if this looks like a company/brand page, not a car model
            if any(kw in desc for kw in CAR_SKIP):
                logger.debug("Skipping Wikipedia '{}' — not a car model page", term)
                continue
            src = (data.get("originalimage") or data.get("thumbnail") or {}).get("source", "")
            if not src:
                continue
            src = re.sub(r'\?.*$', '', src)
            # Use the thumbnail URL as-is (Wikimedia enforces allowed sizes)
            req2 = urllib.request.Request(src, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                img_bytes = resp2.read()
            from PIL import Image
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            path = out_dir / "_car_image.jpg"
            img.save(str(path), format="JPEG", quality=88)
            logger.info("Car image fetched from Wikipedia for '{}'", car_model)
            return path
        except Exception as exc:
            logger.debug("Car image fetch failed for '{}': {}", term, exc)
    return None

router = APIRouter()

# Include document parsing routes
router.include_router(documents_router, tags=["documents"])

# Uploads live next to the project's data folder
_UPLOADS_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

# ── Photo fingerprint cache ────────────────────────────────────────────────────
# Maps a fingerprint of the uploaded photo set → completed job_id.
# When the same photos are uploaded again, we return the cached result instantly
# instead of rescanning — eliminating non-determinism variance across runs.
# Key: frozenset of (filename, file_size_bytes) tuples (order-independent).
# In-memory only — resets on server restart (intentional: restart = fresh start).
_SCAN_CACHE: dict[frozenset, str] = {}   # fingerprint → job_id


def _photo_fingerprint(files_info: list[tuple[str, int]]) -> frozenset:
    """Stable, order-independent fingerprint for a set of uploaded photos."""
    return frozenset(files_info)


# ── POST /audit ────────────────────────────────────────────────────────────────

@router.post("/audit")
async def start_audit(
    files:        list[UploadFile] = File(...),
    plate:        str = Form(""),
    company:      str = Form(""),
    car:          str = Form(""),
    logo_b64:     str = Form(""),      # base64 PNG — company logo from Clearbit
    car_img_b64:  str = Form(""),      # base64 image — car model photo from Wikipedia
):
    """
    Upload photos and start an AI damage audit.
    Returns a job_id immediately — poll GET /audit/{job_id} for progress.
    """
    if not files:
        raise HTTPException(400, "No files uploaded.")

    # Filter to allowed image types
    valid = [f for f in files if Path(f.filename or "").suffix.lower() in _ALLOWED_EXT]
    if not valid:
        raise HTTPException(400, "No valid image files (JPG/PNG/HEIC/WEBP).")

    # ── Fingerprint check — avoid rescanning the same photos ─────────────────
    # Read file sizes from the upload stream without consuming it
    files_info: list[tuple[str, int]] = []
    file_contents: list[bytes] = []
    for upload in valid:
        data = await upload.read()
        file_contents.append(data)
        files_info.append((upload.filename or "", len(data)))

    fingerprint = _photo_fingerprint(files_info)
    if fingerprint in _SCAN_CACHE:
        cached_id = _SCAN_CACHE[fingerprint]
        cached_job = get_job(cached_id)
        if cached_job and cached_job.status.value == "done":
            logger.info("Cache hit: fingerprint matches job {} — returning cached result", cached_id)
            return {
                "job_id":   cached_id,
                "status":   cached_job.status,
                "photos":   len(valid),
                "cached":   True,
            }

    # Create job and photos folder
    job         = new_job()
    photos_dir  = _UPLOADS_DIR / job.id
    photos_dir.mkdir(parents=True, exist_ok=True)
    job.photos_dir = photos_dir

    # Save uploaded files (use already-read content)
    for (upload, data) in zip(valid, file_contents):
        dest = photos_dir / (upload.filename or f"photo_{len(file_contents)}")
        with open(dest, "wb") as f:
            f.write(data)

    # Store fingerprint so this job's result can be reused
    job.fingerprint = fingerprint   # type: ignore[attr-defined]
    _SCAN_CACHE[fingerprint] = job.id

    logger.info("Job {}: {} photo(s) saved to {}", job.id, len(valid), photos_dir)

    # ── Logo: browser-supplied first, then server-side Wikipedia fetch ──────
    logo_path: Path | None = None
    if logo_b64:
        try:
            from PIL import Image as _PIL
            raw = base64.b64decode(logo_b64)
            img = _PIL.open(io.BytesIO(raw)).convert("RGBA")
            logo_path = photos_dir / "_company_logo.png"
            img.save(str(logo_path), format="PNG")
            logger.info("Logo from browser saved OK")
        except Exception as exc:
            logger.warning("Browser logo decode failed: {}", exc)

    if not logo_path:
        logo_path = _fetch_logo_server(company, photos_dir)

    # ── Car image: browser-supplied first, then server-side Wikipedia ────────
    car_img_path: Path | None = None
    if car_img_b64:
        try:
            from PIL import Image as _PIL
            raw = base64.b64decode(car_img_b64)
            img = _PIL.open(io.BytesIO(raw)).convert("RGB")
            car_img_path = photos_dir / "_car_image.jpg"
            img.save(str(car_img_path), format="JPEG", quality=88)
            logger.info("Car image from browser saved OK")
        except Exception as exc:
            logger.warning("Browser car image decode failed: {}", exc)

    if not car_img_path:
        car_img_path = _fetch_car_image_server(car, photos_dir)

    # Start processing in a background thread (pipeline is synchronous / blocking)
    metadata_kwargs = {
        "car_plate":      plate.strip()   or None,
        "rental_company": company.strip() or None,
        "car_model":      car.strip()     or None,
    }
    thread = threading.Thread(
        target=_run_pipeline,
        args=(job, metadata_kwargs, logo_path, car_img_path),
        daemon=True,
    )
    thread.start()

    return {"job_id": job.id, "status": job.status, "photos": len(valid)}


# ── GET /audit/{job_id} ────────────────────────────────────────────────────────

@router.get("/audit/{job_id}")
def job_status(job_id: str):
    """Poll job progress. Returns status, progress message, and results when done."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found.")

    resp: dict = {
        "job_id":   job.id,
        "status":   job.status,
        "progress": job.progress,
    }
    if job.status == JobStatus.DONE:
        resp["damages"]       = job.damages_count
        resp["covered_views"] = job.covered_views
        resp["damage_list"]   = job.damage_list
        resp["report_url"]    = f"/audit/{job.id}/report"
        resp["evidence_url"]  = f"/audit/{job.id}/evidence"
        # Cost tracking
        resp["api_cost_usd"]  = round(job.api_cost_usd, 4)
        resp["api_cost_nis"]  = round(job.api_cost_nis, 2)
        resp["api_calls"]     = {
            "vision": job.vision_calls,
            "text": job.text_calls,
        }
    if job.status == JobStatus.ERROR:
        resp["error"] = job.error_msg

    return JSONResponse(resp)


# ── GET /audit/{job_id}/report ─────────────────────────────────────────────────

@router.get("/audit/{job_id}/report")
def download_report(job_id: str):
    """Download the PDF audit report."""
    job = _get_done_job(job_id)
    if not job.report_pdf or not job.report_pdf.exists():
        raise HTTPException(404, "Report not ready.")
    return FileResponse(
        job.report_pdf,
        media_type="application/pdf",
        filename=f"rentalshield_report_{job_id}.pdf",
    )


# ── GET /audit/{job_id}/evidence ───────────────────────────────────────────────

@router.get("/audit/{job_id}/evidence")
def download_evidence(job_id: str):
    """Download the complete evidence ZIP (photos + report + manifest)."""
    job = _get_done_job(job_id)
    if not job.evidence_zip or not job.evidence_zip.exists():
        raise HTTPException(404, "Evidence package not ready.")
    return FileResponse(
        job.evidence_zip,
        media_type="application/zip",
        filename=job.evidence_zip.name,
    )


# ── Background worker ─────────────────────────────────────────────────────────

def _run_pipeline(job: Job, metadata_kwargs: dict, logo_path: "Path | None" = None, car_img_path: "Path | None" = None) -> None:
    """
    Run the photo audit pipeline in a background thread.
    Updates job.status and job.progress as work progresses.
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        from rentalshield.models import RentalMetadata
        from rentalshield.pipeline import run_photo_audit

        job.status   = JobStatus.PROCESSING
        job.progress = "Starting analysis …"

        metadata = RentalMetadata(**{k: v for k, v in metadata_kwargs.items() if v})

        job.progress = "Scanning photos for damage …"

        session = run_photo_audit(
            photo_dir    = job.photos_dir,
            output_dir   = job.photos_dir.parent,
            metadata     = metadata,
            logo_path    = logo_path,
            car_img_path = car_img_path,
        )

        job.session_dir    = session.video_path.parent if session.video_path else None
        job.damages_count  = len(session.damages)
        job.report_pdf     = session.audit_pdf

        # Locate the evidence ZIP in the session output folder
        if session.audit_pdf:
            session_out = Path(session.audit_pdf).parent
            zips = list(session_out.glob("rentalshield_*.zip"))
            if zips:
                job.evidence_zip = zips[0]

        job.covered_views = session.covered_views   # set by pipeline from AI view field
        job.damage_list   = [
            {
                "photo":       d.frame,
                "type":        d.type.value,
                "location":    d.location,
                "description": d.description,   # full AI description for compare matching
                "severity":    d.severity.value,
            }
            for d in session.damages
        ]

        # Cost tracking
        job.api_cost_usd = session.api_cost_usd
        job.api_cost_nis = session.api_cost_nis
        job.vision_calls = session.vision_calls
        job.text_calls = session.text_calls

        job.status   = JobStatus.DONE
        job.progress = (
            f"Done — {job.damages_count} damage(s) found."
            if job.damages_count
            else "Done — no damage detected."
        )
        logger.info(
            "Job {}: completed ({} damages, ${:.4f} USD / {:.2f} NIS)",
            job.id, job.damages_count, job.api_cost_usd, job.api_cost_nis
        )

    except Exception as exc:
        logger.exception("Job {}: pipeline error — {}", job.id, exc)
        job.status    = JobStatus.ERROR
        job.progress  = "Analysis failed."
        job.error_msg = _friendly_error(exc)


def _friendly_error(exc: Exception) -> str:
    """Translate raw Python exceptions into user-friendly messages.
    RuntimeError messages we raise ourselves are already friendly — pass through.
    """
    raw = str(exc)
    # Our own explicit user-facing errors → keep as-is
    if isinstance(exc, RuntimeError):
        return raw
    # Common failure modes → friendly translations
    low = raw.lower()
    if "429" in raw or "quota" in low or "resource_exhausted" in low:
        return ("The AI service is temporarily rate-limited. "
                "Please wait a minute and try again.")
    if "503" in raw or "unavailable" in low:
        return ("The AI service is temporarily unavailable. "
                "Please try again in a few seconds.")
    if "timeout" in low or "timed out" in low:
        return ("The scan took too long. Check your internet connection "
                "and try again with fewer photos.")
    if "gemini_api_key" in low or "api key" in low:
        return "Server configuration error. Please contact support."
    if "no valid image" in low or "no files" in low:
        return "No usable photos were uploaded. Please try again."
    # Unknown error — give a generic friendly message but keep the raw
    # tail for debugging in the logs.
    return "Something went wrong during analysis. Please try again."


# ── POST /audit/{job_id}/compare ──────────────────────────────────────────────

@router.post("/audit/{job_id}/compare")
async def compare_with_company(
    job_id: str,
    company_pdf: UploadFile = File(...),
):
    """
    Upload the rental company's inspection PDF and compare it against the
    completed audit scan.  Returns a full three-way comparison:
      matched          — both scan and company agree (user is protected)
      extra_protection — user scan found it, company did NOT list (extra protection)
      risk             — company listed it, user scan MISSED it (potential charge risk)
    """
    job = _get_done_job(job_id)

    if not job.damage_list:
        raise HTTPException(422, "No damages recorded in this job — nothing to compare.")

    if not company_pdf.filename or not company_pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF file.")

    # Save the uploaded company PDF next to the job photos
    pdf_dest = job.photos_dir / "_company_contract.pdf"
    with open(pdf_dest, "wb") as f:
        shutil.copyfileobj(company_pdf.file, f)

    logger.info("Job {}: company PDF saved to {}", job_id, pdf_dest)

    # Run comparison in the same thread (fast — two AI text calls, no vision)
    try:
        result = _run_compare(job, pdf_dest)
        job.comparison = result
        return JSONResponse(result)
    except Exception as exc:
        logger.exception("Job {}: compare failed — {}", job_id, exc)
        raise HTTPException(500, f"Comparison failed: {exc}")


@router.get("/audit/{job_id}/compare")
def get_comparison(job_id: str):
    """Return the last comparison result for a job (if any)."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found.")
    if job.comparison is None:
        raise HTTPException(404, "No comparison has been run for this job yet.")
    return JSONResponse(job.comparison)


def _run_compare(job: Job, pdf_path: Path) -> dict:
    """Parse company PDF and run two-way reconciliation. Returns comparison dict."""
    from rentalshield.ai.gemini_analyzer import GeminiAnalyzer
    from rentalshield.compare.pdf_parser import CompanyPDFParser
    from rentalshield.compare.reconciler import DamageReconciler
    from rentalshield.models import Damage, DamageType, Severity

    analyzer  = GeminiAnalyzer()
    parser    = CompanyPDFParser(analyzer)
    reconciler = DamageReconciler(analyzer)

    # Step 1: parse the company's damage list from their PDF
    company_damages = parser.parse(pdf_path)

    # Step 2: reconstruct Damage objects from the job's damage_list
    my_damages = []
    for d in job.damage_list:
        try:
            my_damages.append(Damage(
                type        = DamageType(d.get("type", "OTHER")),
                location    = d.get("location", "unknown"),
                severity    = Severity(d.get("severity", "UNKNOWN")),
                description = d.get("description") or d.get("location", ""),
                frame       = d.get("photo"),
            ))
        except Exception:
            pass

    # Step 3: forward comparison — classify each user scan damage
    forward = reconciler.compare(my_damages, company_damages)

    # Step 4: reverse comparison — find company items user scan missed
    reverse = reconciler.find_company_risks(my_damages, company_damages)

    # Build structured result
    matched          = []
    extra_protection = []
    uncertain        = []

    from rentalshield.models import ComparisonStatus
    for item in forward:
        entry = {
            "location":    item.my_location,
            "type":        item.my_type.value,
            "reason":      item.reason,
        }
        if item.status == ComparisonStatus.MATCHED:
            matched.append(entry)
        elif item.status == ComparisonStatus.NEW:
            extra_protection.append(entry)
        else:
            uncertain.append(entry)

    risk = [
        {
            "location": r.get("location", "—"),
            "type":     r.get("type", "—"),
            "severity": r.get("severity", "UNKNOWN"),
            "notes":    r.get("notes", ""),
            "reason":   r.get("reason", ""),
        }
        for r in reverse
        if not r.get("covered", True)
    ]

    return {
        "company_total":      len(company_damages),
        "scan_total":         len(my_damages),
        "matched":            matched,
        "extra_protection":   extra_protection,
        "risk":               risk,
        "uncertain":          uncertain,
        "company_damages":    company_damages,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_done_job(job_id: str) -> Job:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found.")
    if job.status != JobStatus.DONE:
        raise HTTPException(409, f"Job is not done yet (status: {job.status}).")
    return job
