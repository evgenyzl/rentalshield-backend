"""
Car Profile endpoints (CRUD operations).
Premium-quality responses for beautiful frontend.
"""

from fastapi import APIRouter, Request, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from loguru import logger

from rentalshield.i18n import get_text
from rentalshield.i18n.middleware import get_language
from rentalshield.db.database import get_db
from rentalshield.db.models import CarProfile, RentalSession, SessionTypeEnum, RentalDocument
from sqlalchemy.orm import Session

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS - Premium Response Structure
# ============================================================================

class CarProfileCreate(BaseModel):
    """Create car profile request."""
    rental_provider: str = Field(..., min_length=1, description="e.g., Hertz, Sixt, Avis")
    make: str = Field(..., min_length=1, description="e.g., Ford")
    model: str = Field(..., min_length=1, description="e.g., Focus")
    year: Optional[int] = Field(None, ge=1900, le=2100)
    license_plate: str = Field(..., min_length=1)
    vin: Optional[str] = None
    color: Optional[str] = None
    rental_start_date: datetime
    rental_end_date: datetime
    pickup_location: str = Field(..., min_length=1)
    dropoff_location: str = Field(..., min_length=1)
    mileage_at_pickup: Optional[int] = Field(None, ge=0)

    class Config:
        example = {
            "rental_provider": "Hertz",
            "make": "Ford",
            "model": "Focus",
            "year": 2023,
            "license_plate": "ABC-1234",
            "color": "Silver",
            "rental_start_date": "2026-09-28T10:00:00",
            "rental_end_date": "2026-10-05T10:00:00",
            "pickup_location": "LAX Terminal 3",
            "dropoff_location": "LAX Terminal 1",
        }


class InspectionStatus(BaseModel):
    """Inspection status summary."""
    pickup_complete: bool
    dropoff_complete: bool
    photos_count: int
    documents_count: int
    last_synced: Optional[datetime] = None


class CarProfileDetail(BaseModel):
    """Premium car profile detail response."""
    id: str
    rental_provider: str
    make: str
    model: str
    year: Optional[int]
    license_plate: str
    color: Optional[str]
    rental_start_date: datetime
    rental_end_date: datetime
    pickup_location: str
    dropoff_location: str
    status: str
    inspection_status: InspectionStatus
    created_at: datetime
    updated_at: datetime


class CarProfileSummary(BaseModel):
    """Premium car summary (list view)."""
    id: str
    rental_provider: str
    make: str
    model: str
    license_plate: str
    color: Optional[str]
    status: str
    rental_start_date: datetime
    rental_end_date: datetime
    inspection_status: InspectionStatus


class APIResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool
    message: str
    data: Optional[dict] = None
    language: str


# ============================================================================
# HELPERS
# ============================================================================

def _get_inspection_status(db: Session, car_id: str) -> InspectionStatus:
    """Get inspection status for a car."""
    pickup = db.query(RentalSession).filter(
        RentalSession.car_profile_id == car_id,
        RentalSession.session_type == SessionTypeEnum.PICKUP
    ).first()

    dropoff = db.query(RentalSession).filter(
        RentalSession.car_profile_id == car_id,
        RentalSession.session_type == SessionTypeEnum.DROPOFF
    ).first()

    photos_count = 0
    if pickup and pickup.inspection_photos:
        photos_count += len(pickup.inspection_photos)
    if dropoff and dropoff.inspection_photos:
        photos_count += len(dropoff.inspection_photos)

    documents_count = db.query(RentalDocument).filter(
        RentalDocument.car_profile_id == car_id
    ).count()

    last_synced = None
    if pickup and pickup.updated_at:
        last_synced = pickup.updated_at
    if dropoff and dropoff.updated_at:
        if last_synced is None or dropoff.updated_at > last_synced:
            last_synced = dropoff.updated_at

    return InspectionStatus(
        pickup_complete=bool(pickup and pickup.is_complete),
        dropoff_complete=bool(dropoff and dropoff.is_complete),
        photos_count=photos_count,
        documents_count=documents_count,
        last_synced=last_synced,
    )


def _to_detail(car: CarProfile, db: Session) -> CarProfileDetail:
    """Convert to detail response."""
    return CarProfileDetail(
        id=car.id,
        rental_provider=car.rental_provider,
        make=car.make,
        model=car.model,
        year=car.year,
        license_plate=car.license_plate,
        color=car.color,
        rental_start_date=car.rental_start_date,
        rental_end_date=car.rental_end_date,
        pickup_location=car.pickup_location,
        dropoff_location=car.dropoff_location,
        status=car.status,
        inspection_status=_get_inspection_status(db, car.id),
        created_at=car.created_at,
        updated_at=car.updated_at,
    )


def _to_summary(car: CarProfile, db: Session) -> CarProfileSummary:
    """Convert to summary response."""
    return CarProfileSummary(
        id=car.id,
        rental_provider=car.rental_provider,
        make=car.make,
        model=car.model,
        license_plate=car.license_plate,
        color=car.color,
        status=car.status,
        rental_start_date=car.rental_start_date,
        rental_end_date=car.rental_end_date,
        inspection_status=_get_inspection_status(db, car.id),
    )


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/", response_model=APIResponse)
async def list_cars(
    request: Request,
    db: Session = Depends(get_db),
):
    """List user's car profiles (sorted: active first)."""
    lang = get_language(request)

    try:
        user_id = "temp_user_id"  # TODO: Get from JWT

        cars = db.query(CarProfile).filter(
            CarProfile.user_id == user_id
        ).order_by(
            CarProfile.status.desc(),
            CarProfile.rental_end_date.desc()
        ).all()

        summaries = [_to_summary(car, db).dict() for car in cars]

        return APIResponse(
            success=True,
            message=get_text("common.success", language=lang),
            data={"cars": summaries, "count": len(summaries)},
            language=lang,
        )

    except Exception as e:
        logger.error("List cars error: {}", e, exc_info=True)
        raise HTTPException(500, detail=get_text("errors.serverError", language=lang))


@router.post("/", response_model=APIResponse, status_code=201)
async def create_car(
    request: Request,
    payload: CarProfileCreate,
    db: Session = Depends(get_db),
):
    """Create new car profile."""
    lang = get_language(request)

    try:
        user_id = "temp_user_id"  # TODO: Get from JWT

        if payload.rental_start_date >= payload.rental_end_date:
            raise HTTPException(400, detail="Start date must be before end date")

        existing = db.query(CarProfile).filter(
            CarProfile.user_id == user_id,
            CarProfile.license_plate == payload.license_plate
        ).first()

        if existing:
            raise HTTPException(400, detail="License plate already registered")

        car = CarProfile(
            user_id=user_id,
            rental_provider=payload.rental_provider,
            make=payload.make,
            model=payload.model,
            year=payload.year,
            license_plate=payload.license_plate,
            vin=payload.vin,
            color=payload.color,
            rental_start_date=payload.rental_start_date,
            rental_end_date=payload.rental_end_date,
            pickup_location=payload.pickup_location,
            dropoff_location=payload.dropoff_location,
            mileage_at_pickup=payload.mileage_at_pickup,
            status="active",
        )

        db.add(car)
        db.commit()
        db.refresh(car)

        logger.info("✓ Car created: {} ({})", car.license_plate, car.id)

        return APIResponse(
            success=True,
            message=get_text("common.success", language=lang),
            data=_to_detail(car, db).dict(),
            language=lang,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Create car error: {}", e, exc_info=True)
        db.rollback()
        raise HTTPException(500, detail=get_text("errors.serverError", language=lang))


@router.get("/{car_id}", response_model=APIResponse)
async def get_car(
    request: Request,
    car_id: str,
    db: Session = Depends(get_db),
):
    """Get car profile detail."""
    lang = get_language(request)

    try:
        car = db.query(CarProfile).filter(CarProfile.id == car_id).first()

        if not car:
            raise HTTPException(404, detail="Car not found")

        return APIResponse(
            success=True,
            message=get_text("common.success", language=lang),
            data=_to_detail(car, db).dict(),
            language=lang,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get car error: {}", e, exc_info=True)
        raise HTTPException(500, detail=get_text("errors.serverError", language=lang))


@router.patch("/{car_id}", response_model=APIResponse)
async def update_car(
    request: Request,
    car_id: str,
    payload: dict,
    db: Session = Depends(get_db),
):
    """Update car profile."""
    lang = get_language(request)

    try:
        car = db.query(CarProfile).filter(CarProfile.id == car_id).first()

        if not car:
            raise HTTPException(404, detail="Car not found")

        for key, value in payload.items():
            if value is not None and hasattr(car, key):
                setattr(car, key, value)

        car.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(car)

        logger.info("✓ Car updated: {}", car.license_plate)

        return APIResponse(
            success=True,
            message=get_text("common.success", language=lang),
            data=_to_detail(car, db).dict(),
            language=lang,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Update car error: {}", e, exc_info=True)
        db.rollback()
        raise HTTPException(500, detail=get_text("errors.serverError", language=lang))


@router.delete("/{car_id}", response_model=APIResponse)
async def delete_car(
    request: Request,
    car_id: str,
    db: Session = Depends(get_db),
):
    """Delete car profile."""
    lang = get_language(request)

    try:
        car = db.query(CarProfile).filter(CarProfile.id == car_id).first()

        if not car:
            raise HTTPException(404, detail="Car not found")

        plate = car.license_plate
        db.delete(car)
        db.commit()

        logger.info("✓ Car deleted: {}", plate)

        return APIResponse(
            success=True,
            message=get_text("common.success", language=lang),
            data={"deleted_car_id": car_id},
            language=lang,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete car error: {}", e, exc_info=True)
        db.rollback()
        raise HTTPException(500, detail=get_text("errors.serverError", language=lang))
