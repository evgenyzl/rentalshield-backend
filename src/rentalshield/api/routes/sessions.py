"""
Rental Session endpoints (Pickup/Dropoff inspections).
Premium-quality responses with inspection tracking.
"""

from fastapi import APIRouter, Request, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from loguru import logger

from rentalshield.i18n import get_text
from rentalshield.i18n.middleware import get_language
from rentalshield.db.database import get_db
from rentalshield.db.models import RentalSession, SessionTypeEnum, CarProfile
from sqlalchemy.orm import Session

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS - Premium Response Structure
# ============================================================================

class PreExistingDamage(BaseModel):
    """Pre-existing damage item."""
    location: str = Field(..., description="e.g., 'front bumper'")
    description: str = Field(..., description="e.g., 'small scratch'")
    severity: str = Field(..., description="minor, moderate, or major")

    class Config:
        example = {
            "location": "front bumper",
            "description": "small scratch",
            "severity": "minor"
        }


class SessionCreate(BaseModel):
    """Create rental session request."""
    car_id: str = Field(..., description="Car profile ID")
    session_type: str = Field(..., description="pickup or dropoff")
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_address: Optional[str] = None
    pre_existing_damages: Optional[List[PreExistingDamage]] = None

    class Config:
        example = {
            "car_id": "uuid-123",
            "session_type": "pickup",
            "gps_latitude": 33.9425,
            "gps_longitude": -118.4081,
            "gps_address": "LAX Terminal 3",
            "pre_existing_damages": [
                {
                    "location": "front bumper",
                    "description": "small scratch",
                    "severity": "minor"
                }
            ]
        }


class SessionDetail(BaseModel):
    """Premium session detail response."""
    id: str
    car_id: str
    session_type: str
    timestamp: datetime
    gps_latitude: Optional[float]
    gps_longitude: Optional[float]
    gps_address: Optional[str]
    pre_existing_damages: Optional[List[dict]]
    is_complete: bool
    completed_at: Optional[datetime]
    photos_captured: int
    sync_status: str
    created_at: datetime
    updated_at: datetime


class SessionSummary(BaseModel):
    """Session summary for list view."""
    id: str
    car_id: str
    session_type: str
    timestamp: datetime
    is_complete: bool
    photos_captured: int
    gps_address: Optional[str]
    sync_status: str


class APIResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool
    message: str
    data: Optional[dict] = None
    language: str


# ============================================================================
# HELPERS
# ============================================================================

def _to_detail(session: RentalSession) -> SessionDetail:
    """Convert to detail response."""
    photos_count = len(session.inspection_photos) if session.inspection_photos else 0
    
    return SessionDetail(
        id=session.id,
        car_id=session.car_profile_id,
        session_type=session.session_type.value,
        timestamp=session.timestamp,
        gps_latitude=session.gps_latitude,
        gps_longitude=session.gps_longitude,
        gps_address=session.gps_address,
        pre_existing_damages=session.pre_existing_damages,
        is_complete=session.is_complete,
        completed_at=session.completed_at,
        photos_captured=photos_count,
        sync_status=session.sync_status.value,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _to_summary(session: RentalSession) -> SessionSummary:
    """Convert to summary response."""
    photos_count = len(session.inspection_photos) if session.inspection_photos else 0
    
    return SessionSummary(
        id=session.id,
        car_id=session.car_profile_id,
        session_type=session.session_type.value,
        timestamp=session.timestamp,
        is_complete=session.is_complete,
        photos_captured=photos_count,
        gps_address=session.gps_address,
        sync_status=session.sync_status.value,
    )


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/", response_model=APIResponse, status_code=201)
async def create_session(
    request: Request,
    payload: SessionCreate,
    db: Session = Depends(get_db),
):
    """Create new rental session (pickup or dropoff)."""
    lang = get_language(request)

    try:
        # Verify car exists
        car = db.query(CarProfile).filter(CarProfile.id == payload.car_id).first()
        if not car:
            raise HTTPException(404, detail="Car profile not found")

        # Validate session type
        try:
            session_type = SessionTypeEnum(payload.session_type)
        except ValueError:
            raise HTTPException(400, detail="Invalid session type (pickup or dropoff)")

        # Check if session already exists for this type
        existing = db.query(RentalSession).filter(
            RentalSession.car_profile_id == payload.car_id,
            RentalSession.session_type == session_type
        ).first()

        if existing and existing.is_complete:
            raise HTTPException(400, detail=f"{payload.session_type} inspection already completed")

        # Create session
        session = RentalSession(
            car_profile_id=payload.car_id,
            session_type=session_type,
            timestamp=datetime.utcnow(),
            gps_latitude=payload.gps_latitude,
            gps_longitude=payload.gps_longitude,
            gps_address=payload.gps_address,
            pre_existing_damages=[d.dict() for d in payload.pre_existing_damages] if payload.pre_existing_damages else None,
            is_complete=False,
            sync_status="pending",
        )

        db.add(session)
        db.commit()
        db.refresh(session)

        logger.info("✓ Session created: {} {} ({})", car.license_plate, payload.session_type, session.id)

        return APIResponse(
            success=True,
            message=get_text("common.success", language=lang),
            data=_to_detail(session).dict(),
            language=lang,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Create session error: {}", e, exc_info=True)
        db.rollback()
        raise HTTPException(500, detail=get_text("errors.serverError", language=lang))


@router.get("/{session_id}", response_model=APIResponse)
async def get_session(
    request: Request,
    session_id: str,
    db: Session = Depends(get_db),
):
    """Get rental session detail."""
    lang = get_language(request)

    try:
        session = db.query(RentalSession).filter(RentalSession.id == session_id).first()

        if not session:
            raise HTTPException(404, detail="Session not found")

        return APIResponse(
            success=True,
            message=get_text("common.success", language=lang),
            data=_to_detail(session).dict(),
            language=lang,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get session error: {}", e, exc_info=True)
        raise HTTPException(500, detail=get_text("errors.serverError", language=lang))


@router.patch("/{session_id}/complete", response_model=APIResponse)
async def complete_session(
    request: Request,
    session_id: str,
    db: Session = Depends(get_db),
):
    """Mark session as complete."""
    lang = get_language(request)

    try:
        session = db.query(RentalSession).filter(RentalSession.id == session_id).first()

        if not session:
            raise HTTPException(404, detail="Session not found")

        if session.is_complete:
            raise HTTPException(400, detail="Session already completed")

        session.is_complete = True
        session.completed_at = datetime.utcnow()
        session.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(session)

        car = db.query(CarProfile).filter(CarProfile.id == session.car_profile_id).first()
        logger.info("✓ Session completed: {} {} ({})", 
                   car.license_plate if car else "unknown", 
                   session.session_type.value, 
                   session.id)

        return APIResponse(
            success=True,
            message=get_text("common.success", language=lang),
            data=_to_detail(session).dict(),
            language=lang,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Complete session error: {}", e, exc_info=True)
        db.rollback()
        raise HTTPException(500, detail=get_text("errors.serverError", language=lang))


@router.get("/car/{car_id}/all", response_model=APIResponse)
async def list_car_sessions(
    request: Request,
    car_id: str,
    db: Session = Depends(get_db),
):
    """List all sessions for a car (pickup & dropoff)."""
    lang = get_language(request)

    try:
        # Verify car exists
        car = db.query(CarProfile).filter(CarProfile.id == car_id).first()
        if not car:
            raise HTTPException(404, detail="Car profile not found")

        sessions = db.query(RentalSession).filter(
            RentalSession.car_profile_id == car_id
        ).order_by(
            RentalSession.timestamp.desc()
        ).all()

        summaries = [_to_summary(s).dict() for s in sessions]

        return APIResponse(
            success=True,
            message=get_text("common.success", language=lang),
            data={
                "car_id": car_id,
                "sessions": summaries,
                "count": len(summaries)
            },
            language=lang,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("List sessions error: {}", e, exc_info=True)
        raise HTTPException(500, detail=get_text("errors.serverError", language=lang))


@router.get("/type/{car_id}/{session_type}", response_model=APIResponse)
async def get_session_by_type(
    request: Request,
    car_id: str,
    session_type: str,
    db: Session = Depends(get_db),
):
    """Get pickup or dropoff session for a car."""
    lang = get_language(request)

    try:
        # Validate session type
        try:
            s_type = SessionTypeEnum(session_type)
        except ValueError:
            raise HTTPException(400, detail="Invalid session type (pickup or dropoff)")

        session = db.query(RentalSession).filter(
            RentalSession.car_profile_id == car_id,
            RentalSession.session_type == s_type
        ).first()

        if not session:
            # Return empty session structure if not created yet
            return APIResponse(
                success=True,
                message=get_text("common.success", language=lang),
                data={"session": None, "status": "not_started"},
                language=lang,
            )

        return APIResponse(
            success=True,
            message=get_text("common.success", language=lang),
            data=_to_detail(session).dict(),
            language=lang,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get session by type error: {}", e, exc_info=True)
        raise HTTPException(500, detail=get_text("errors.serverError", language=lang))
