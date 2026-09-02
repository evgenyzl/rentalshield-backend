"""
Core data models for RentalShield.
All data flowing through the pipeline uses these types.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field


class DamageType(str, Enum):
    SCRATCH = "SCRATCH"
    DENT    = "DENT"
    CHIP    = "CHIP"
    CRACK   = "CRACK"
    SCUFF   = "SCUFF"
    RUST    = "RUST"
    MISSING = "MISSING"
    OTHER   = "OTHER"


class Severity(str, Enum):
    MINOR    = "MINOR"
    MODERATE = "MODERATE"
    SEVERE   = "SEVERE"
    UNKNOWN  = "UNKNOWN"


class BoundingBox(BaseModel):
    """Damage location within a frame, as fractions of image size (0–1)."""
    x_pct: float = Field(default=0.1, ge=0.0, le=1.0)
    y_pct: float = Field(default=0.1, ge=0.0, le=1.0)
    w_pct: float = Field(default=0.2, ge=0.0, le=1.0)
    h_pct: float = Field(default=0.2, ge=0.0, le=1.0)


class Damage(BaseModel):
    """A single detected damage item."""
    type:           DamageType
    location:       str
    severity:       Severity
    description:    str
    confidence:     float = Field(default=1.0, ge=0.0, le=1.0)  # AI certainty (0–1)
    time_sec:       Optional[float] = None
    frame:          Optional[int]   = None
    bbox:           Optional[BoundingBox] = None
    img_path:       Optional[Path]  = None   # crop thumbnail (used in PDF table)
    full_img_path:  Optional[Path]  = None   # full annotated frame (primary legal evidence)

    def to_export_dict(self) -> dict:
        """JSON-serialisable dict for saving between scripts."""
        return {
            "type":        self.type.value,
            "location":    self.location,
            "severity":    self.severity.value,
            "description": self.description,
            "time_sec":    self.time_sec,
            "frame":       self.frame,
            "img_path":    str(self.img_path) if self.img_path else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Damage":
        return cls(
            type        = DamageType(d["type"]),
            location    = d["location"],
            severity    = Severity(d.get("severity", "UNKNOWN")),
            description = d["description"],
            time_sec    = d.get("time_sec"),
            frame       = d.get("frame"),
            img_path    = Path(d["img_path"]) if d.get("img_path") else None,
        )


class ComparisonStatus(str, Enum):
    MATCHED   = "MATCHED"    # company already documented this area
    NEW       = "NEW"        # NOT in company PDF — you need protection!
    UNCERTAIN = "UNCERTAIN"  # hard to match from descriptions alone


class ComparisonItem(BaseModel):
    """Result of comparing one of your damages against the company's list."""
    my_index:      int
    my_location:   str
    my_type:       DamageType
    my_description: str
    status:        ComparisonStatus
    reason:        str
    img_path:      Optional[Path] = None


class RentalMetadata(BaseModel):
    """
    Optional rental-context info shown in every report header.
    All fields are optional so scans work without them too.
    """
    rental_company:   Optional[str]   = None   # e.g. "Hertz", "Sixt", "Europcar"
    car_plate:        Optional[str]   = None   # license plate number (auto-detected or manual)
    car_plate_source: Optional[str]   = None   # "auto" | "manual"
    car_model:        Optional[str]   = None   # e.g. "Citroën C3", "VW Golf"
    location:         Optional[str]   = None   # pickup location, e.g. "BCN Airport T1"
    contract_number:  Optional[str]   = None   # rental agreement / booking ref
    inspector_name:   Optional[str]   = None   # person doing the inspection
    gps_lat:          Optional[float] = None   # GPS latitude
    gps_lon:          Optional[float] = None   # GPS longitude

    def any_set(self) -> bool:
        return any(v for v in self.model_dump().values())

    @property
    def maps_url(self) -> Optional[str]:
        if self.gps_lat is not None and self.gps_lon is not None:
            return f"https://maps.google.com/?q={self.gps_lat:.6f},{self.gps_lon:.6f}"
        return None


class AuditSession(BaseModel):
    """Everything produced by a single video audit run."""
    session_id:    str
    video_path:    Path
    created_at:    datetime = Field(default_factory=datetime.now)
    recorded_at:   Optional[datetime] = None   # when the VIDEO was filmed (from MP4 metadata)
    damages:       list[Damage] = Field(default_factory=list)
    audit_pdf:     Optional[Path] = None
    metadata:      Optional[RentalMetadata] = None
    covered_views: list[str] = Field(default_factory=list)  # e.g. ["front","rear","left_side"]

    @property
    def new_damage_count(self) -> int:
        return len(self.damages)


class ComparisonSession(BaseModel):
    """Everything produced by a company-PDF comparison run."""
    session_id:      str
    audit_session_id: str
    company_pdf:     Path
    created_at:      datetime = Field(default_factory=datetime.now)
    company_damages: list[dict] = Field(default_factory=list)
    comparison:      list[ComparisonItem] = Field(default_factory=list)
    report_pdf:      Optional[Path] = None

    @property
    def new_damages(self) -> list[ComparisonItem]:
        return [c for c in self.comparison if c.status == ComparisonStatus.NEW]

    @property
    def matched_damages(self) -> list[ComparisonItem]:
        return [c for c in self.comparison if c.status == ComparisonStatus.MATCHED]

    @property
    def uncertain_damages(self) -> list[ComparisonItem]:
        return [c for c in self.comparison if c.status == ComparisonStatus.UNCERTAIN]
