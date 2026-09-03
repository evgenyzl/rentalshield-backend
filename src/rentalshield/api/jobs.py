"""
In-memory job tracker for the RentalShield API.

Each audit run is a "job" with a unique ID. The browser uploads photos,
gets back a job ID immediately, then polls /audit/{job_id} until done.

This is intentionally simple — a dict + asyncio.Lock is fine for a single
server instance. When we move to the cloud we swap this for Redis or a DB.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class JobStatus(str, Enum):
    QUEUED     = "queued"
    PROCESSING = "processing"
    DONE       = "done"
    ERROR      = "error"


@dataclass
class Job:
    id:          str
    created_at:  datetime     = field(default_factory=datetime.now)
    status:      JobStatus    = JobStatus.QUEUED
    progress:    str          = "Waiting to start …"
    photos_dir:  Optional[Path] = None   # folder of uploaded originals
    session_dir: Optional[Path] = None   # pipeline output folder
    report_pdf:  Optional[Path] = None   # audit_report.pdf
    evidence_zip: Optional[Path] = None  # rentalshield_*.zip
    damages_count: int = 0
    covered_views: list[str] = field(default_factory=list)
    damage_list:  list[dict] = field(default_factory=list)   # [{type, location, severity, photo}]
    error_msg:   Optional[str] = None
    # Cost tracking (Gemini API usage)
    api_cost_usd: float = 0.0         # Total API cost in USD
    api_cost_nis: float = 0.0         # Total API cost in NIS (USD * 3.67)
    vision_calls: int = 0              # Number of vision API calls
    text_calls: int = 0                # Number of text API calls
    # Comparison data (set after POST /audit/{job_id}/compare)
    comparison:  Optional[dict] = None   # full comparison result JSON


# ── Global store ──────────────────────────────────────────────────────────────

_store: dict[str, Job] = {}
_lock  = asyncio.Lock()


def new_job() -> Job:
    job = Job(id=uuid.uuid4().hex[:12])
    _store[job.id] = job
    return job


def get_job(job_id: str) -> Optional[Job]:
    return _store.get(job_id)


def all_jobs() -> list[Job]:
    return list(_store.values())
