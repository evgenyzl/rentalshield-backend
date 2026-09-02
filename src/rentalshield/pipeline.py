"""
RentalShield pipeline orchestrator.
All the logic lives in the individual modules; this ties them together.
Designed to be importable from a future FastAPI server with minimal changes.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import cv2
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from rentalshield.config import settings
from rentalshield.models import Damage, AuditSession, ComparisonSession, RentalMetadata
from rentalshield.video.extractor import VideoExtractor
from rentalshield.ai.factory import get_analyzer
from rentalshield.ai.pdf_parser import RentalPDFParser
from rentalshield.compare.reconciler import DamageReconciler
from rentalshield.report.generator import generate_audit_report, generate_comparison_report
from rentalshield.utils.image import save_damage_images
from rentalshield.ai.plate_detector import detect_plate
from rentalshield.photo.quality import assess, enhance
from rentalshield.ai.crop_validator import validate_crop
from rentalshield.ai.component_identifier import refine_location
from rentalshield.video.extractor import get_recording_time, get_gps_from_video

console = Console()


def _session_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ── Audit pipeline ─────────────────────────────────────────────────────────────

def run_audit(
    video_path:       Path,
    output_dir:       Path | None = None,
    frame_interval_s: float | None = None,
    metadata:         RentalMetadata | None = None,
) -> AuditSession:
    """
    Full audit pipeline:  video → frame extraction → AI Vision → PDF + JSON.

    Parameters
    ----------
    video_path       : path to the car walkthrough video
    output_dir       : where to write the session folder (defaults to settings)
    frame_interval_s : seconds between analyzed frames (defaults to settings)
    metadata         : optional rental context (plate, company, location, …)

    Returns
    -------
    AuditSession with all detected damages and the path to the generated PDF.
    """
    settings.validate()
    settings.ensure_dirs()

    session_id = _session_id()
    out_dir    = (output_dir or settings.sessions_dir) / session_id
    crops_dir  = out_dir / "crops"
    out_dir.mkdir(parents=True, exist_ok=True)
    crops_dir.mkdir(parents=True, exist_ok=True)

    interval = frame_interval_s or settings.frame_interval_s

    console.rule("[bold red]RentalShield — Visual Damage Audit[/bold red]")
    console.print(f"[dim]Session:[/dim] {session_id}")
    console.print(f"[dim]Video:[/dim]   {video_path.name}")
    if metadata and metadata.any_set():
        if metadata.rental_company: console.print(f"[dim]Company:[/dim]  {metadata.rental_company}")
        if metadata.car_plate:      console.print(f"[dim]Plate:[/dim]    {metadata.car_plate}")
        if metadata.car_model:      console.print(f"[dim]Car:[/dim]      {metadata.car_model}")
        if metadata.location:       console.print(f"[dim]Location:[/dim] {metadata.location}")
    console.print()

    extractor   = VideoExtractor(video_path, interval_s=interval)
    analyzer    = get_analyzer()
    recorded_at = get_recording_time(video_path)
    if recorded_at:
        console.print(f"[dim]Recorded:[/dim]  {recorded_at.strftime('%Y-%m-%d  %H:%M:%S  %Z')}")

    # Auto-fill GPS from video metadata if not supplied manually
    if metadata is None:
        metadata = RentalMetadata()
    if metadata.gps_lat is None:
        gps = get_gps_from_video(video_path)
        if gps:
            metadata.gps_lat, metadata.gps_lon = gps
            console.print(f"[green]✓[/green] GPS from video: {metadata.gps_lat:.5f}, {metadata.gps_lon:.5f}")
    console.print(f"[dim]Provider:[/dim]  {settings.ai_provider.upper()}")

    # ── Auto-detect licence plate ─────────────────────────────────────────────
    if not metadata.car_plate:
        console.print("[dim]Reading licence plate from video …[/dim]")
        plate = detect_plate(video_path, analyzer)
        if plate:
            metadata.car_plate        = plate
            metadata.car_plate_source = "auto"
            console.print(f"[green]✓[/green] Plate detected: [bold]{plate}[/bold]")
        else:
            console.print("[dim]Plate not readable from video (set manually with --plate)[/dim]")

    session = AuditSession(
        session_id  = session_id,
        video_path  = video_path,
        metadata    = metadata,
        recorded_at = recorded_at,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning frames …", total=extractor.sample_count)

        for frame_no, time_sec, frame in extractor.frames():
            progress.update(
                task,
                advance=1,
                description=f"[cyan]{time_sec:.1f}s[/cyan] frame {frame_no}",
            )

            damages = analyzer.analyze_frame(frame, frame_no, time_sec)

            for damage in damages:
                full_path, crop_path    = save_damage_images(frame, damage, crops_dir, frame_no)
                damage.img_path         = crop_path   # thumbnail used in PDF table
                damage.full_img_path    = full_path   # full annotated frame
                session.damages.append(damage)

            if damages:
                console.print(
                    f"  [yellow]⚠[/yellow]  [{time_sec:.1f}s]  "
                    + ", ".join(f"{d.type.value} — {d.location}" for d in damages)
                )

    console.print()
    console.print(f"[bold]Raw detections:[/bold] {len(session.damages)}")

    # ── Crop validation — second AI pass ─────────────────────────────────────
    # Show each saved crop to the AI and ask: "is this actually a car panel?"
    # Drops false positives that slipped through the edge-density pre-filter
    # and the frame-level valid/reason check.
    if session.damages:
        console.print("[dim]Validating crops …[/dim]")
        validated  = []
        rejected   = []
        last_call  = [0.0]   # shared mutable tracker — enforces min gap between calls
        for damage in session.damages:
            if damage.img_path and Path(damage.img_path).exists():
                if validate_crop(Path(damage.img_path), analyzer, last_call):
                    validated.append(damage)
                else:
                    rejected.append(damage)
                    # Remove the false-positive crop image
                    try:
                        Path(damage.img_path).unlink()
                    except OSError:
                        pass
            else:
                validated.append(damage)   # no crop → keep (shouldn't happen)

        if rejected:
            console.print(
                f"  [yellow]⚠[/yellow]  Rejected {len(rejected)} false positive(s): "
                + ", ".join(Path(d.img_path).stem for d in rejected)
            )
        session.damages = validated

    console.print(f"[bold]Confirmed damages:[/bold] {len(session.damages)}")

    # Save raw JSON (used by compare script)
    json_path = out_dir / "damages.json"
    with open(json_path, "w") as f:
        json.dump([d.to_export_dict() for d in session.damages], f, indent=2)
    console.print(f"[dim]Saved:[/dim] {json_path}")

    # Generate PDF
    pdf_path = out_dir / "audit_report.pdf"
    generate_audit_report(
        damages     = session.damages,
        output_pdf  = pdf_path,
        video_name  = video_path.name,
        session_id  = session_id,
        metadata    = metadata,
        recorded_at = recorded_at,
    )
    session.audit_pdf = pdf_path
    console.print(f"[green]✓[/green] Audit report → {pdf_path}")

    return session


# ── Cross-photo duplicate consolidation ───────────────────────────────────────

_CONSOLIDATE_PROMPT = """\
You are a car damage auditor reviewing findings from a walkaround inspection.
The SAME physical damage can appear in multiple photos taken from slightly different angles.
Your job is to remove only clear, unambiguous duplicates — keep everything else.

Damage list (JSON):
{damage_json}

TASK:
1. Identify findings that are CERTAINLY the same physical damage seen from different photos.
2. For each duplicate group, keep the ONE entry with the highest confidence or most detail.
3. Return a JSON array of integer IDs to KEEP.

STRICT MERGING RULES — err on the side of KEEPING, not merging:
- Only merge when BOTH conditions hold:
    a) Same damage TYPE (both DENT, or both SCRATCH, or both SCUFF — NOT mixed types)
    b) Same location wording that clearly refers to the identical spot on the car.
- Wording variations of the EXACT same spot may be merged, for example:
    "rear quarter panel near fuel filler cap"  ==  "fuel filler cap area, passenger side"
    "front bumper, passenger side"  ==  "front bumper passenger corner"

HARD RULES — never override these:
- NEVER merge different damage types (a SCRATCH and a SCUFF at the same spot are two separate damages).
- NEVER merge different sides of the car (driver vs. passenger).
- NEVER merge front vs. rear locations (front bumper ≠ rear bumper).
- NEVER merge damages from the SAME photo — if two findings are from the same photo number they were already detected as distinct items.
- When in doubt, KEEP both — a false merge loses real evidence; a false duplicate is harmless.

Output ONLY the JSON array of IDs to keep, nothing else. Example: [0, 2, 4, 7, 9]
"""


def _consolidate_damages(damages, analyzer, console) -> list:
    """
    Send the full damage list to the AI and ask it which entries are cross-photo
    duplicates. Returns the filtered list with duplicates removed.
    Falls back to the original list if the AI call fails or returns bad data.
    """
    numbered = [
        {
            "id":          i,
            "photo":       d.frame,
            "type":        d.type.value,
            "location":    d.location,
            "severity":    d.severity.value,
            "description": d.description,
            "confidence":  round(d.confidence, 2),
        }
        for i, d in enumerate(damages)
    ]
    prompt = _CONSOLIDATE_PROMPT.format(damage_json=json.dumps(numbered, indent=2))

    try:
        raw = analyzer.generate_text(prompt)
        # Extract JSON array from response (model may wrap it in ```json … ```)
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON array in response")
        keep_ids: list[int] = json.loads(raw[start:end])
        if not isinstance(keep_ids, list):
            raise ValueError("Response is not a list")
        keep_set = set(int(x) for x in keep_ids)
        result = [d for i, d in enumerate(damages) if i in keep_set]
        if not result:   # sanity — never return empty
            raise ValueError("AI returned empty keep list")
        return result
    except Exception as exc:
        logger.warning("Consolidation failed ({}), keeping all damages", exc)
        console.print(f"  [yellow]⚠[/yellow]  Consolidation skipped: {exc}")
        return damages


# ── Deterministic dedup passes ─────────────────────────────────────────────────

_NOISE_WORDS = {
    "panel", "area", "zone", "section", "surface", "region",
    "the", "a", "an", "of", "on", "in", "at", "paint",
}

# Car landmarks — two damages that share a landmark AND same type AND same side
# are almost certainly the same physical damage seen from different angles.
_LANDMARKS = [
    "fuel filler cap", "fuel flap", "fuel cap",
    # wheel arch and wheel trim are DIFFERENT parts — do NOT share a landmark
    "wheel arch", "wheel well",
    "door handle", "door sill",
    "wing mirror", "side mirror",
    "headlight", "tail light", "taillight", "fog light",
    "windscreen", "windshield",
    "roof rail", "door frame",
    # NOTE: "bumper corner" / "bumper lip" removed from landmarks — rear bumper
    # and front bumper are different zones even though both say "bumper".
]

_SIDE_WORDS = {
    "driver":    "driver",
    "passenger": "passenger",
    "front":     "front",
    "rear":      "rear",
    "left":      "driver",    # normalise
    "right":     "passenger",
}


def _loc_key(loc: str) -> str:
    """Normalise a location string to a comparable key."""
    words = loc.lower().replace("/", " ").replace(",", " ").replace("-", " ").split()
    return " ".join(w for w in words if w not in _NOISE_WORDS)


def _side(loc: str) -> str | None:
    """Extract car side from a location string."""
    l = loc.lower()
    for word, side in _SIDE_WORDS.items():
        if word in l:
            return side
    return None


def _shares_landmark(loc1: str, loc2: str) -> bool:
    l1, l2 = loc1.lower(), loc2.lower()
    return any(lm in l1 and lm in l2 for lm in _LANDMARKS)


def _string_dedup(damages: list) -> list:
    """
    Pass 1 — exact location-key match.
    Catches same damage described with trivially different wording
    (e.g. #10 / #11 from same photo, same location label).
    Keeps the entry with higher confidence.
    """
    merged: dict[tuple, object] = {}
    for d in damages:
        key = (d.type.value, _loc_key(d.location))
        if key not in merged or d.confidence > merged[key].confidence:
            merged[key] = d
    return list(merged.values())


def _landmark_dedup(damages: list) -> list:
    """
    Pass 2 — landmark proximity match.
    Catches cross-photo duplicates like 'left of fuel filler cap' vs
    'behind fuel filler cap' — same type + same side + shared landmark.
    Keeps the entry with the higher confidence.
    """
    kept: list = []
    for d in damages:
        is_dup = False
        for existing in kept:
            if (d.type == existing.type
                    and _side(d.location) == _side(existing.location)
                    and _shares_landmark(d.location, existing.location)):
                # Replace if this one has higher confidence
                if d.confidence > existing.confidence:
                    idx = kept.index(existing)
                    kept[idx] = d
                is_dup = True
                break
        if not is_dup:
            kept.append(d)
    return kept


# ── Photo audit pipeline ───────────────────────────────────────────────────────

def run_photo_audit(
    photo_dir:    Path,
    output_dir:   Path | None = None,
    metadata:     RentalMetadata | None = None,
    logo_path:    Path | None = None,
    car_img_path: Path | None = None,
) -> AuditSession:
    """
    Photo-based audit pipeline: folder of images → AI analysis → PDF report.
    Identical to run_audit() but accepts photos instead of a video.
    Better quality than video — 12MP phone photos vs 1080p frames.
    """
    from rentalshield.photo.extractor import PhotoExtractor

    settings.validate()
    settings.ensure_dirs()

    session_id = _session_id()
    out_dir    = (output_dir or settings.sessions_dir) / session_id
    crops_dir  = out_dir / "crops"
    out_dir.mkdir(parents=True, exist_ok=True)
    crops_dir.mkdir(parents=True, exist_ok=True)

    console.rule("[bold red]RentalShield — Photo Damage Audit[/bold red]")
    console.print(f"[dim]Session:[/dim] {session_id}")
    console.print(f"[dim]Photos:[/dim]  {photo_dir}")

    extractor   = PhotoExtractor(photo_dir)
    analyzer    = get_analyzer()
    recorded_at = extractor.get_first_capture_time()
    if recorded_at:
        console.print(f"[dim]Taken at:[/dim] {recorded_at.strftime('%Y-%m-%d  %H:%M:%S')}")

    if metadata is None:
        metadata = RentalMetadata()

    # Auto-fill GPS from photo EXIF if not supplied manually
    if metadata.gps_lat is None:
        gps = extractor.get_gps()
        if gps:
            metadata.gps_lat, metadata.gps_lon = gps
            console.print(f"[green]✓[/green] GPS from photo: {metadata.gps_lat:.5f}, {metadata.gps_lon:.5f}")

    # Plate is detected during the main damage scan — no separate pre-pass needed.
    # Each analyze_frame call returns the plate if visible; we pick it up in the loop below.
    console.print(f"[dim]Provider:[/dim] {settings.ai_provider.upper()}")
    console.print()

    # ── Pre-flight: is this actually a car? ─────────────────────────────────
    # One cheap yes/no vision call on the first photo. If it's clearly not a
    # car (screenshot, indoor scene, selfie), abort BEFORE spending tokens on
    # the full damage-scan pipeline (~150 API calls for 21 photos).
    first_frame = extractor.first_frame()
    if first_frame is not None:
        try:
            if not analyzer.is_car(first_frame):
                console.print("[red]✗[/red]  Pre-flight: first photo is not a car — aborting scan.")
                logger.warning("Pre-flight rejected: first photo doesn't look like a car")
                raise RuntimeError(
                    "The first photo doesn't look like a car. "
                    "Please take clear photos of the vehicle exterior and try again."
                )
            console.print("[green]✓[/green]  Pre-flight: car detected — proceeding.")
        except RuntimeError:
            raise
        except Exception as exc:
            # Pre-check failed for network/API reasons — fail-open, let full scan run
            logger.warning("Pre-flight check errored — proceeding anyway: {}", exc)

    session = AuditSession(
        session_id  = session_id,
        video_path  = photo_dir,   # re-use field; means "source path"
        metadata    = metadata,
        recorded_at = recorded_at,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Analysing photos …", total=extractor.sample_count)

        covered_views: set[str] = set()   # tracks which car angles were photographed
        # Best full-car shot from the uploaded photos — used as report header image.
        # Preference: front > rear > left_side/right_side (broadest car coverage first).
        # Among multiple photos of the same view, pick the one with fewest damages found
        # (overview shots capture less detail → fewer AI detections; close-ups = more).
        _VIEW_PREF = {"front": 0, "rear": 1, "left_side": 2, "right_side": 3}
        car_ref_photo: "dict[str, list]" = {}   # view → [(damage_count, path)]

        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout, as_completed as _zone_completed

        # Per-photo captured view/plate (set by _analyze_with_timeout inside the
        # sub-thread that runs analyze_frame — cannot use thread-local on the
        # analyzer because that sub-thread has its own storage that the parent
        # worker cannot see. Instead we plumb the values back explicitly).
        _capture: "dict[int, dict]" = {}

        def _analyze_with_timeout(frame, photo_no, timeout=45, is_zone=False):
            """Run analyze_frame in a thread with a hard timeout.
            Returns [] if the call hangs longer than timeout seconds.
            is_zone=True uses the zone-sensitive prompt (lower confidence threshold).
            Side-effect: for main-scan calls (is_zone=False), captures view/plate
            into _capture[photo_no] before returning to the parent thread.
            """
            def _wrapped():
                dmgs = analyzer.analyze_frame(
                    frame, photo_no, 0.0, True, is_zone,
                )
                # Grab view/plate WHILE STILL IN THE SUB-THREAD — that's the only
                # thread where analyzer's thread-local storage has the value we set.
                if not is_zone:
                    v = getattr(analyzer, "last_seen_view", None)
                    p = getattr(analyzer, "last_seen_plate", None)
                    slot = _capture.setdefault(photo_no, {})
                    # Only update when we got a non-empty value — a follow-up
                    # pass on the same photo may return None; don't clobber.
                    if v:
                        slot["view"] = v
                    if p:
                        slot["plate"] = p
                return dmgs

            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(_wrapped)
                try:
                    return future.result(timeout=timeout)
                except FutureTimeout:
                    logger.warning(
                        "Photo {} timed out after {}s — skipping",
                        photo_no, timeout,
                    )
                    return []
                except Exception as exc:
                    logger.error("Photo {} error in thread: {}", photo_no, exc)
                    return []

        def _analyze_photo_twice(frame, photo_no, timeout=45):
            """Analyze the same photo twice and merge the results.

            Optimization: only run second pass if first pass has borderline detections.
            If all detections are high-confidence (>= 0.85), skip second pass (save $).
            If any detection is borderline (0.65–0.85), run second pass to catch flips.

            Running twice eliminates borderline non-determinism:
            a damage whose confidence flips around 0.70 (threshold) will be caught
            in at least one of the two passes and retained.

            When both passes find the same damage (same type + similar location),
            we keep the higher-confidence version's data.
            """
            run1 = _analyze_with_timeout(frame, photo_no, timeout=timeout)

            # Optimization: skip second pass if first pass is very confident
            _CONFIDENT_THRESHOLD = 0.85  # skip re-scan if all detections > this
            if run1 and all(dmg.confidence >= _CONFIDENT_THRESHOLD for dmg in run1):
                logger.debug("Photo {}: all detections high-confidence (>= {}) — skipping second pass",
                           photo_no, _CONFIDENT_THRESHOLD)
                return run1

            run2 = _analyze_with_timeout(frame, photo_no, timeout=timeout)

            counts = f"pass 1→{len(run1)}, pass 2→{len(run2)}"

            if not run2:
                logger.debug("Photo {}: only pass 1 returned results ({})", photo_no, counts)
                return run1
            if not run1:
                logger.debug("Photo {}: only pass 2 returned results ({})", photo_no, counts)
                return run2

            # Merge the two passes.
            # Key insight: a damage seen in BOTH passes is almost certainly real —
            # boost its confidence by 15% so it survives downstream filtering.
            # A damage seen in only ONE pass must have confidence > SINGLE_PASS_MIN
            # to be kept — this is the main lever against non-determinism variance.
            # Raising SINGLE_PASS_MIN reduces the damage count but makes it stable.
            #
            # Location normalisation: strip noise words that the AI varies between passes
            # ("rear door panel" vs "rear door" → same key).
            _NOISE = {"panel", "area", "zone", "section", "surface", "region"}
            _CONFIDENCE_BOOST  = 1.15   # reward for appearing in both runs
            _SINGLE_PASS_MIN   = 0.75   # single-pass detections need high confidence

            def _loc_key(loc: str) -> str:
                words = loc.lower().strip().split()
                return " ".join(w for w in words if w not in _NOISE)

            # Index run1 by key (only keep high-confidence single-pass entries)
            run1_map: dict[tuple, "Damage"] = {}
            for dmg in run1:
                if dmg.confidence < _SINGLE_PASS_MIN:
                    continue   # will get another chance if run2 also finds it
                key = (dmg.type, _loc_key(dmg.location))
                if key not in run1_map or dmg.confidence > run1_map[key].confidence:
                    run1_map[key] = dmg

            # Keep ALL of run1 for the cross-run matching step (temp map)
            run1_all: dict[tuple, "Damage"] = {}
            for dmg in run1:
                key = (dmg.type, _loc_key(dmg.location))
                if key not in run1_all or dmg.confidence > run1_all[key].confidence:
                    run1_all[key] = dmg

            merged: dict[tuple, "Damage"] = dict(run1_map)

            for dmg in run2:
                key = (dmg.type, _loc_key(dmg.location))
                if key in run1_all:
                    # Seen in BOTH passes — always keep, boost confidence
                    best = dmg if dmg.confidence > run1_all[key].confidence else run1_all[key]
                    import copy
                    boosted = copy.copy(best)
                    boosted.confidence = min(1.0, best.confidence * _CONFIDENCE_BOOST)
                    merged[key] = boosted
                elif dmg.confidence >= _SINGLE_PASS_MIN:
                    # New in run2 only — keep only if confidence is high enough
                    merged[key] = dmg
                # else: low-confidence single-pass → discard

            result = list(merged.values())
            new_count = len(result) - max(len(run1), len(run2))
            if new_count > 0:
                console.print(
                    f"  [green]+[/green]  Photo {photo_no}: double-scan caught "
                    f"[bold]{new_count}[/bold] extra damage(s) missed in one pass "
                    f"({counts})"
                )
                logger.info(
                    "Photo {}: double-scan found {} extra damage(s) missed in one pass ({})",
                    photo_no, new_count, counts,
                )
            else:
                logger.debug("Photo {}: double-scan consistent ({})", photo_no, counts)
            return result

        # Zone-split helper — used by _process_one_photo()
        def _split_zones(f):
            h, w = f.shape[:2]
            zh, zw = int(h * 0.50), int(w * 0.50)
            return [
                ("TL", f[0:zh,           0:zw]),
                ("TR", f[0:zh,           w - zw:w]),
                ("BL", f[h - zh:h,       0:zw]),
                ("BR", f[h - zh:h,       w - zw:w]),
                ("BC", f[h - zh:h,       zw // 2:w - zw // 2]),
            ]

        _WIDE_VIEWS = {"front", "rear", "left_side", "right_side"}

        def _process_one_photo(photo_no, cap_time, frame):
            """Run the full per-photo pipeline. Thread-safe — uses only local state
            plus thread-local analyzer.last_seen_*. Returns aggregation dict."""
            # ── Quality gate + enhancement ────────────────────────────────
            quality = assess(frame)
            if quality.notes:
                frame_ = enhance(frame, quality)
                quality = assess(frame_)
            else:
                frame_ = frame
            if not quality.is_usable:
                return {"photo_no": photo_no, "skipped": True,
                        "reason": f"too dark or blurry ({quality.label})"}

            damages = _analyze_photo_twice(frame_, photo_no, timeout=45)

            # Read view/plate captured inside the analyze sub-thread (see _capture).
            # Safe across parallel photo workers because keys are per photo_no.
            _slot = _capture.get(photo_no, {})
            seen_view       = _slot.get("view")
            seen_plate      = _slot.get("plate")
            _main_dmg_count = len(damages)

            # For compressed images: always run zones to catch missed detail.
            # ONLY skip zone analysis if damage count is very high (>12),
            # which likely indicates false positives or an extremely damaged car.
            # Zones help catch subtle damage on compressed photos (e.g. WhatsApp).
            _run_zones = _main_dmg_count < 12
            zone_extra: list = []
            if _run_zones:
                with ThreadPoolExecutor(max_workers=5) as _zex:
                    _zfuts = {
                        _zex.submit(_analyze_with_timeout, zf, photo_no, 35, True): lbl
                        for lbl, zf in _split_zones(frame_)
                    }
                    for _zfut in _zone_completed(_zfuts):
                        _zd = _zfut.result() or []
                        if _zd:
                            zone_extra.extend(_zd)

            if zone_extra:
                _existing = {(d.type, _loc_key(d.location)) for d in damages}
                new_from_zones = [d for d in zone_extra
                                  if (d.type, _loc_key(d.location)) not in _existing]
                damages.extend(new_from_zones)

            # Save damage images (paths keyed by photo_no → no collisions)
            for damage in damages:
                damage.frame    = photo_no
                damage.time_sec = None
                full_path, crop_path = save_damage_images(frame_, damage, crops_dir, photo_no)
                damage.img_path      = crop_path
                damage.full_img_path = full_path

            return {
                "photo_no":        photo_no,
                "skipped":         False,
                "damages":         damages,
                "seen_view":       seen_view,
                "seen_plate":      seen_plate,
                "main_dmg_count":  _main_dmg_count,
            }

        # ── Parallel main loop (2 photos concurrent) ────────────────────────
        # Aggregate results in photo_no order after all workers complete.
        # 2 workers = sweet spot: fast enough, safely under Gemini free-tier
        # RPM quota. 3+ workers trigger 429 rate-limits → 180s backoff → slower.
        _PHOTO_CONCURRENCY = 2
        photos_input = list(extractor.frames())
        results_by_no: dict[int, dict] = {}

        with ThreadPoolExecutor(max_workers=_PHOTO_CONCURRENCY) as _pex:
            _pfuts = {
                _pex.submit(_process_one_photo, pn, ct, fr): pn
                for pn, ct, fr in photos_input
            }
            for _pfut in _zone_completed(_pfuts):
                pn = _pfuts[_pfut]
                try:
                    results_by_no[pn] = _pfut.result()
                except Exception as exc:
                    logger.error("Photo {} failed in parallel worker: {}", pn, exc)
                    results_by_no[pn] = {"photo_no": pn, "skipped": True,
                                          "reason": f"worker error: {exc}"}
                progress.update(task, advance=1,
                                description=f"[cyan]Photo {pn}[/cyan]")

        # Aggregate in photo order (deterministic for header selection, plate)
        for photo_no in sorted(results_by_no.keys()):
            r = results_by_no[photo_no]
            if r.get("skipped"):
                console.print(
                    f"  [red]✗[/red]  Photo {photo_no}: {r.get('reason','skipped')}"
                )
                continue
            damages         = r["damages"]
            seen_view       = r["seen_view"]
            seen_plate      = r["seen_plate"]
            _main_dmg_count = r["main_dmg_count"]

            if seen_view:
                covered_views.add(seen_view)
                if seen_view in _VIEW_PREF:
                    car_ref_photo.setdefault(seen_view, []).append(
                        (_main_dmg_count, extractor.paths[photo_no - 1])
                    )
            car_ref_photo.setdefault("_any", []).append(
                (_main_dmg_count, extractor.paths[photo_no - 1])
            )

            if not metadata.car_plate and seen_plate:
                metadata.car_plate        = seen_plate
                metadata.car_plate_source = "auto"
                console.print(
                    f"  [green]✓[/green] Plate detected in photo {photo_no}: [bold]{seen_plate}[/bold]"
                )

            for damage in damages:
                session.damages.append(damage)

            if damages:
                console.print(
                    f"  [yellow]⚠[/yellow]  Photo {photo_no}: "
                    + ", ".join(f"{d.type.value} — {d.location}" for d in damages)
                )

    if not metadata.car_plate:
        console.print("[dim]Plate not readable from photos (set manually with --plate)[/dim]")

    # ── Coverage check — warn about missing car angles ────────────────────────
    _REQUIRED_VIEWS = {"front", "rear", "left_side", "right_side"}
    _OPTIONAL_VIEWS = {"roof", "wheels"}
    _VIEW_LABELS = {
        "front":      "Front  (bumper, headlights, bonnet)",
        "rear":       "Rear   (bumper, tail lights, boot)",
        "left_side":  "Left side  (driver doors & panels)",
        "right_side": "Right side (passenger doors & panels)",
        "roof":       "Roof",
        "wheels":     "Wheels / tyres",
    }
    missing_required = _REQUIRED_VIEWS - covered_views
    missing_optional = _OPTIONAL_VIEWS - covered_views

    console.print()
    if covered_views:
        covered_labels = [_VIEW_LABELS.get(v, v) for v in sorted(covered_views)]
        console.print(f"[dim]Coverage:[/dim] {', '.join(covered_labels)}")

    if missing_required:
        console.print(
            "\n[bold red]⚠  COVERAGE GAPS — damage in these areas CANNOT be documented:[/bold red]"
        )
        for v in sorted(missing_required):
            console.print(f"   [red]✗[/red]  {_VIEW_LABELS[v]}")
        console.print(
            "   [dim]Tip: re-photograph the car and include these angles before returning it.[/dim]"
        )
    elif missing_optional:
        console.print("[green]✓[/green] All four sides covered.")
    else:
        console.print("[green]✓[/green] Full coverage — all angles documented.")

    if missing_optional:
        console.print("[dim]  Also consider photographing:[/dim]")
        for v in sorted(missing_optional):
            console.print(f"   [dim]-  {_VIEW_LABELS[v]}[/dim]")

    console.print()
    console.print(f"[bold]Raw detections:[/bold] {len(session.damages)}")

    # ── Crop validation (parallel) ─────────────────────────────────────────────
    # Run all crop checks concurrently — each gets a fresh rate-limit tracker so
    # the per-call 5 s gap is local to that one call (no inter-thread sleeping).
    if session.damages:
        from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed
        console.print("[dim]Validating crops …[/dim]")

        def _check_crop(dmg):
            if dmg.img_path and Path(dmg.img_path).exists():
                ok = validate_crop(Path(dmg.img_path), analyzer, [0.0])
                return dmg, ok
            return dmg, True   # no image → keep by default

        rejected: list = []
        keep_ids: set  = set()
        with ThreadPoolExecutor(max_workers=4) as _ex:
            futs = {_ex.submit(_check_crop, d): d for d in session.damages}
            for fut in _as_completed(futs):
                dmg, ok = fut.result()
                if ok:
                    keep_ids.add(id(dmg))
                else:
                    rejected.append(dmg)
                    try:
                        Path(dmg.img_path).unlink()
                    except OSError:
                        pass

        if rejected:
            console.print(
                f"  [yellow]⚠[/yellow]  Rejected {len(rejected)} false positive(s): "
                + ", ".join(Path(d.img_path).stem for d in rejected if d.img_path)
            )
        # Preserve original order
        session.damages = [d for d in session.damages if id(d) in keep_ids]

    console.print(f"[bold]Confirmed damages:[/bold] {len(session.damages)}")

    # ── Dedup — three passes before component refinement ─────────────────
    # Run while location labels are still broad — easier to match.
    if len(session.damages) >= 2:
        console.print("[dim]Deduplicating cross-photo findings …[/dim]")
        before = len(session.damages)

        # Pass 1: deterministic string match (same type + same normalised location)
        session.damages = _string_dedup(session.damages)

        # Pass 2: deterministic landmark match (same type + same side + shared landmark)
        session.damages = _landmark_dedup(session.damages)

        # Pass 3: AI consolidation — catches anything the rules missed
        session.damages = _consolidate_damages(session.damages, analyzer, console)

        removed = before - len(session.damages)
        if removed:
            console.print(
                f"  [green]✓[/green]  Removed {removed} duplicate(s) "
                f"({before} → {len(session.damages)})"
            )
        else:
            console.print("  [dim]No duplicates found.[/dim]")

    # ── Component identification (parallel) ───────────────────────────────────
    # The main scan names the broad zone ("rear quarter panel").
    # This pass sends each full annotated frame to the AI asking only:
    # "What exact component is in the red box?" → "rear window rubber seal", etc.
    # Skipped automatically if the daily API quota is exhausted.
    # Each worker gets a fresh rate-limit tracker — no inter-thread sleeping.
    if session.damages:
        from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed2
        console.print("[dim]Identifying components …[/dim]")

        def _refine_one(dmg):
            lc = [0.0]   # fresh per call — no rate-limit sleep between workers
            refined = refine_location(dmg, analyzer, lc)
            quota_hit = lc[0] == float("inf")
            return dmg, refined, quota_hit

        refinements: dict = {}
        quota_exhausted = False
        with ThreadPoolExecutor(max_workers=4) as _ex:
            futs = [_ex.submit(_refine_one, d) for d in session.damages]
            for fut in _as_completed2(futs):
                dmg, refined, hit = fut.result()
                if hit:
                    quota_exhausted = True
                if refined:
                    refinements[id(dmg)] = (dmg, refined)

        if quota_exhausted:
            console.print("  [dim]Component identification skipped — daily quota exhausted[/dim]")

        # Cross-validation: if refinement contradicts what the AI said in the
        # description, the bounding box was pointing to the wrong area — DROP
        # the damage rather than presenting inconsistent info to the customer.
        _BODY_KEYWORDS = {
            "bumper", "fender", "door", "hood", "bonnet", "trunk", "boot",
            "tailgate", "roof", "quarter", "wing", "sill", "rocker",
            "pillar", "panel", "arch", "spoiler", "skirt",
            "wheel", "rim", "tire", "tyre",
            "mirror", "handle",
            "window", "glass", "windshield", "windscreen",
            "headlight", "taillight", "tail light", "fog light", "light",
            "grille", "grill",
            "seal", "weatherstrip", "trim", "moulding", "molding",
            "cap", "flap", "filler",   # fuel filler cap
            "badge", "emblem", "logo",
            "antenna", "wiper", "sunroof",
        }
        def _kw_set(txt: str) -> set:
            low = (txt or "").lower()
            return {kw for kw in _BODY_KEYWORDS if kw in low}

        _kept: list = []
        _dropped_mismatch = 0
        for damage in session.damages:
            entry = refinements.get(id(damage))
            if entry:
                _, refined = entry
                # TODO: re-enable keyword mismatch check after fixing component_identifier
                # refiner — it currently makes too many bad refinement calls that contradict
                # valid descriptions (e.g. says "c-pillar" when description clearly says "bumper").
                # Contradiction check disabled for now. Re-enable with smarter logic.
                old_loc = damage.location
                damage.location = refined
                logger.debug("Component refined: '{}' → '{}'", old_loc, refined)
                console.print(
                    f"  [cyan]↳[/cyan]  Photo {damage.frame}: {old_loc} → [bold]{refined}[/bold]"
                )
            _kept.append(damage)
        session.damages = _kept

    # ── Post-refinement same-frame dedup ─────────────────────────────────────
    # Component identification may rename two separate detections from the SAME
    # photo to the same component (e.g. "front bumper" + "front bumper lower
    # corner" → both become "bumper lip / bumper panel, driver side").
    # We merge only when BOTH the photo frame AND the refined location match —
    # never across photos, which would drop genuinely different physical dents.
    if len(session.damages) >= 2:
        before_post = len(session.damages)
        seen_frame: dict = {}   # (frame, type, loc_key) → best damage
        deduped_post: list = []
        for dmg in session.damages:
            key = (dmg.frame, dmg.type, _loc_key(dmg.location))
            if key not in seen_frame:
                seen_frame[key] = dmg
                deduped_post.append(dmg)
            else:
                # Keep the one with higher confidence; drop the other
                prev = seen_frame[key]
                if dmg.confidence > prev.confidence:
                    deduped_post[deduped_post.index(prev)] = dmg
                    seen_frame[key] = dmg
        session.damages = deduped_post
        removed_post = before_post - len(session.damages)
        if removed_post:
            console.print(
                f"  [green]✓[/green]  Post-refinement dedup removed {removed_post} same-photo duplicate(s)"
            )

    json_path = out_dir / "damages.json"
    with open(json_path, "w") as f:
        json.dump([d.to_export_dict() for d in session.damages], f, indent=2)
    console.print(f"[dim]Saved:[/dim] {json_path}")

    # ── Pick car reference image ──────────────────────────────────────────────
    # Prefer the user's own photo (actual car) over the Wikipedia stock image.
    # Strategy:
    #   1. Prefer a photo where the AI identified the car view (front/rear/side).
    #      Among those, prefer: front > rear > left_side > right_side.
    #      Tie-break: fewest damages from the main scan (wide overview shots
    #      capture fewer damage details than close-ups).
    #   2. Fall back to the "_any" bucket (all photos) and pick fewest damages.
    best_car_img = car_img_path   # Wikipedia / None fallback
    chosen_view  = None
    for view in ("front", "rear", "left_side", "right_side"):
        if view in car_ref_photo:
            best_car_img = min(car_ref_photo[view], key=lambda x: x[0])[1]
            chosen_view  = view
            break
    if not chosen_view and "_any" in car_ref_photo:
        # No view detected for any photo — pick the one with fewest main-scan damages
        best_car_img = min(car_ref_photo["_any"], key=lambda x: x[0])[1]
        chosen_view  = "_any"
    if best_car_img and chosen_view:
        bucket = car_ref_photo.get(chosen_view, [])
        logger.info(
            "Header image: view='{}' photo='{}' ({} candidate(s), picked fewest-damage)",
            chosen_view, best_car_img.name, len(bucket),
        )

    pdf_path = out_dir / "audit_report.pdf"
    generate_audit_report(
        damages      = session.damages,
        output_pdf   = pdf_path,
        video_name   = f"{extractor.sample_count} photos from {photo_dir.name}",
        session_id   = session_id,
        metadata     = metadata,
        recorded_at  = recorded_at,
        logo_path    = logo_path,
        car_img_path = best_car_img,
    )
    session.audit_pdf = pdf_path
    console.print(f"[green]✓[/green] Audit report → {pdf_path}")

    session.covered_views = sorted(covered_views)

    # ── Evidence package ──────────────────────────────────────────────────────
    try:
        from rentalshield.evidence.package import create_evidence_package
        zip_path = create_evidence_package(
            session       = session,
            photo_dir     = photo_dir,
            covered_views = covered_views,
            output_dir    = out_dir,
        )
        console.print(f"[green]✓[/green] Evidence package → {zip_path}")
    except Exception as exc:
        logger.warning("Evidence package failed (non-fatal): {}", exc)

    return session


# ── Comparison pipeline ────────────────────────────────────────────────────────

def run_comparison(
    audit_session: AuditSession | None = None,
    damages_json:  Path | None         = None,
    company_pdf:   Path | None         = None,
    output_dir:    Path | None         = None,
) -> ComparisonSession:
    """
    Comparison pipeline: your damages + company PDF → protection report.

    Either pass an AuditSession object (chained directly after run_audit)
    or a damages_json path (running standalone).
    """
    settings.validate()

    if audit_session:
        my_damages   = audit_session.damages
        audit_id     = audit_session.session_id
    elif damages_json:
        with open(damages_json) as f:
            raw = json.load(f)
        my_damages = [Damage.from_dict(d) for d in raw]
        audit_id   = damages_json.parent.name
    else:
        raise ValueError("Provide either audit_session or damages_json.")

    company_pdf_path = company_pdf or (
        settings.reports_dir / "rental_company_report.pdf"
    )

    session_id = _session_id()
    out_dir    = (output_dir or settings.sessions_dir) / f"{session_id}_compare"
    out_dir.mkdir(parents=True, exist_ok=True)

    console.rule("[bold blue]RentalShield — Protection Report[/bold blue]")
    console.print(f"[dim]Session:[/dim]     {session_id}")
    console.print(f"[dim]Your damages:[/dim] {len(my_damages)}")
    console.print(f"[dim]Company PDF:[/dim]  {company_pdf_path.name}")
    console.print()

    analyzer    = get_analyzer()
    console.print(f"[dim]Provider:[/dim]  {settings.ai_provider.upper()}")
    parser      = RentalPDFParser(analyzer)
    reconciler  = DamageReconciler(analyzer)

    company_damages = parser.parse_damages(company_pdf_path)
    console.print(f"[dim]Company listed:[/dim] {len(company_damages)} damage(s)")

    comparison = reconciler.compare(my_damages, company_damages)

    comp_session = ComparisonSession(
        session_id        = session_id,
        audit_session_id  = audit_id,
        company_pdf       = company_pdf_path,
        company_damages   = company_damages,
        comparison        = comparison,
    )

    pdf_path = out_dir / "protection_report.pdf"
    generate_comparison_report(
        comparison        = comparison,
        company_damages   = company_damages,
        my_damage_count   = len(my_damages),
        output_pdf        = pdf_path,
        audit_pdf_name    = f"Session {audit_id}",
        company_pdf_name  = company_pdf_path.name,
        session_id        = session_id,
    )
    comp_session.report_pdf = pdf_path

    new = comp_session.new_damages

    if not my_damages and company_damages:
        # ── Most dangerous outcome: we documented nothing, company has a list ──
        # "You are covered" would be completely wrong here — we have no photos
        # that prove any of the company's claimed damages were pre-existing.
        console.print(
            f"\n[bold red]⚠  WARNING: You documented 0 damages.[/bold red]"
        )
        console.print(
            f"   The company listed [bold]{len(company_damages)}[/bold] damage(s) on their report."
        )
        console.print(
            "   Without your own photos and documentation, you [bold]cannot dispute[/bold]"
        )
        console.print("   any of these charges if the company raises them at return.")
        console.print()
        console.print("   [dim]What to do:[/dim]")
        console.print("   [dim]  1. Re-photograph the car covering all sides (front, rear, left, right).[/dim]")
        console.print("   [dim]  2. Get close to any visible damage.[/dim]")
        console.print("   [dim]  3. Re-run the audit before returning the vehicle.[/dim]")

    elif new:
        # ── We found damage the company did NOT document ─────────────────────
        # This is actually good for the customer — we have photos proving
        # this damage existed at pickup before the company noticed it.
        console.print(
            f"\n[bold yellow]⚠  {len(new)} damage(s) you found are NOT in the company PDF.[/bold yellow]"
        )
        console.print(
            "   Your photos PROTECT you — these were pre-existing at pickup:"
        )
        for item in new:
            console.print(f"   • {item.my_type.value}  —  {item.my_location}")

    elif not my_damages and not company_damages:
        # ── Both sides found nothing — clean car ─────────────────────────────
        console.print(
            "\n[bold green]✓ No damages found by either party. Car appears clean.[/bold green]"
        )

    else:
        # ── We found damage and it all matches the company's list ─────────────
        matched = len(comp_session.matched_damages)
        console.print(
            f"\n[bold green]✓ All {matched} damage(s) you documented are already "
            f"on the company's report. You are covered.[/bold green]"
        )

    console.print(f"\n[green]✓[/green] Protection report → {pdf_path}")

    # ── Auto-log test result ───────────────────────────────────────────────────
    try:
        from rentalshield.testing.test_log import log_comparison
        matched_count = len([r for r in comparison if r.status.value == "MATCHED"])
        entry = log_comparison(
            audit_session_id = audit_id,
            car_plate        = audit_session.metadata.car_plate if audit_session else None,
            car_model        = audit_session.metadata.car_model if audit_session else None,
            rental_company   = audit_session.metadata.rental_company if audit_session else None,
            company_pdf      = str(company_pdf_path),
            company_count    = len(company_damages),
            our_count        = len(my_damages),
            matched          = matched_count,
            new_undocumented = len(new),
        )
        console.print(
            f"[dim]📋 Logged → recall {entry['recall_pct']}%  |  "
            f"{entry['new_undocumented']} undocumented found  "
            f"(run: python scripts/test_log.py to see all)[/dim]"
        )
    except Exception as exc:
        logger.debug("test_log: could not log comparison — {}", exc)

    return comp_session


# ── CLI entry points ───────────────────────────────────────────────────────────

def audit_cli() -> None:
    """Entry point: rs-audit  [video_path]  [--plate X] [--company X] …"""
    import argparse

    parser = argparse.ArgumentParser(
        description="RentalShield — run visual damage audit on a car video"
    )
    parser.add_argument(
        "video", nargs="?",
        default=str(settings.videos_dir / "car_rental_video.mp4"),
        help="Path to the car walkthrough video",
    )
    parser.add_argument("--interval", "-i", type=float, default=None,
                        help="Seconds between analyzed frames (default: from config)")

    # ── Rental metadata ──────────────────────────────────────────────────────
    meta = parser.add_argument_group("Rental info (shown in report header)")
    meta.add_argument("--plate",    "-p", default=None, metavar="ABC-123",
                      help="Licence plate number")
    meta.add_argument("--company",  "-c", default=None, metavar="Hertz",
                      help="Rental company name")
    meta.add_argument("--car",            default=None, metavar="Citroën C3",
                      help="Car make and model")
    meta.add_argument("--location", "-l", default=None, metavar="BCN Airport T1",
                      help="Pickup location")
    meta.add_argument("--contract",       default=None, metavar="HZ-8834921",
                      help="Rental contract / booking reference")
    meta.add_argument("--inspector",      default=None, metavar="Your Name",
                      help="Name of the person doing the inspection")
    meta.add_argument("--lat",  type=float, default=None, metavar="41.2971",
                      help="GPS latitude  (phone app sets this automatically)")
    meta.add_argument("--lon",  type=float, default=None, metavar="2.0785",
                      help="GPS longitude (phone app sets this automatically)")

    args = parser.parse_args()

    metadata = RentalMetadata(
        car_plate       = args.plate,
        rental_company  = args.company,
        car_model       = args.car,
        location        = args.location,
        contract_number = args.contract,
        inspector_name  = args.inspector,
        gps_lat         = args.lat,
        gps_lon         = args.lon,
    )

    session = run_audit(Path(args.video), frame_interval_s=args.interval,
                        metadata=metadata)
    console.print(f"\nSession ID: [bold]{session.session_id}[/bold]")
    console.print(f"To compare with company PDF, run:  rs-compare {session.session_id}")


def compare_cli() -> None:
    """Entry point: rs-compare  [session_id | damages.json]  [company.pdf]"""
    import argparse

    parser = argparse.ArgumentParser(
        description="RentalShield — compare your audit with the company PDF"
    )
    parser.add_argument(
        "audit", nargs="?", default=None,
        help="Session ID or path to damages.json from the audit step",
    )
    parser.add_argument(
        "--pdf", "-p", default=None,
        help="Path to the rental company's condition PDF",
    )
    args = parser.parse_args()

    damages_json = None
    if args.audit:
        candidate = Path(args.audit)
        if not candidate.exists():
            # Try treating it as a session ID
            candidate = settings.sessions_dir / args.audit / "damages.json"
        if not candidate.exists():
            console.print(f"[red]Cannot find damages file: {args.audit}[/red]")
            sys.exit(1)
        damages_json = candidate

    company_pdf = Path(args.pdf) if args.pdf else None
    run_comparison(damages_json=damages_json, company_pdf=company_pdf)
