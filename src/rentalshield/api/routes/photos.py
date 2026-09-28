"""
Inspection photo upload and management endpoints.
Handles 8-angle photo capture with EXIF extraction and optimization.
"""

from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File, Form, status
from pydantic import BaseModel, Field
from loguru import logger
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from pathlib import Path
import os
import uuid

from rentalshield.i18n import get_text
from rentalshield.i18n.middleware import get_language
from rentalshield.db.database import get_db
from rentalshield.db.models import (
    InspectionPhoto, RentalSession, CarProfile, SyncQueueItem,
    AngleCodeEnum, UploadStatusEnum, SyncQueueActionEnum
)

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class PhotoMetadata(BaseModel):
    """Photo metadata for responses."""
    timestamp: Optional[datetime] = Field(None, description="When photo was taken")
    gps_latitude: Optional[float] = Field(None, description="GPS latitude")
    gps_longitude: Optional[float] = Field(None, description="GPS longitude")
    gps_accuracy_meters: Optional[float] = Field(None, description="GPS accuracy")
    exif_device_make: Optional[str] = Field(None, description="Device manufacturer")
    exif_device_model: Optional[str] = Field(None, description="Device model")
    is_tampered: bool = Field(False, description="Tampering detected?")


class PhotoDetail(BaseModel):
    """Detailed photo response."""
    id: str = Field(..., description="Photo ID")
    rental_session_id: str = Field(..., description="Session ID")
    angle_code: str = Field(..., description="Angle code (FRONT, REAR, etc.)")
    angle_description: Optional[str] = Field(None, description="Human description")
    original_filename: str = Field(..., description="Original filename")
    local_uri: str = Field(..., description="Local storage path")
    cloud_uri: Optional[str] = Field(None, description="Cloud storage path")
    timestamp: datetime = Field(..., description="Upload timestamp")
    image_quality: str = Field(..., description="Quality assessment")
    is_blurry: bool = Field(..., description="Blurry?")
    is_dark: bool = Field(..., description="Dark?")
    upload_status: str = Field(..., description="pending, uploading, uploaded, error")
    metadata: PhotoMetadata = Field(..., description="EXIF and GPS data")
    created_at: datetime = Field(..., description="Created timestamp")

    class Config:
        from_attributes = True


class PhotoSummary(BaseModel):
    """Summary photo response (for lists)."""
    id: str = Field(..., description="Photo ID")
    angle_code: str = Field(..., description="Angle code")
    upload_status: str = Field(..., description="Upload status")
    image_quality: str = Field(..., description="Quality")
    is_blurry: bool = Field(...)
    is_dark: bool = Field(...)
    created_at: datetime = Field(...)

    class Config:
        from_attributes = True


class PhotoListResponse(BaseModel):
    """List photos response."""
    success: bool = Field(True, description="Success status")
    message: str = Field(..., description="Status message")
    data: dict = Field(..., description="Response data")
    language: str = Field(..., description="User language")

    class Config:
        example = {
            "success": True,
            "message": "Success",
            "data": {
                "photos": [
                    {
                        "id": "uuid",
                        "angle_code": "FRONT",
                        "upload_status": "uploaded",
                        "image_quality": "high",
                        "is_blurry": False,
                        "is_dark": False,
                        "created_at": "2026-09-28T10:00:00"
                    }
                ],
                "count": 1,
                "session_id": "uuid"
            },
            "language": "en"
        }


class PhotoUploadResponse(BaseModel):
    """Photo upload response."""
    success: bool = Field(..., description="Success status")
    message: str = Field(..., description="Status message")
    data: dict = Field(..., description="Response data")
    language: str = Field(..., description="User language")

    class Config:
        example = {
            "success": True,
            "message": "Success",
            "data": {
                "id": "uuid",
                "rental_session_id": "uuid",
                "angle_code": "FRONT",
                "angle_description": "Front view of car",
                "original_filename": "photo_2026-09-28_100000.jpg",
                "local_uri": "file:///storage/photos/uuid.jpg",
                "upload_status": "pending",
                "image_quality": "high",
                "is_blurry": False,
                "is_dark": False,
                "metadata": {
                    "timestamp": "2026-09-28T10:00:00",
                    "gps_latitude": 33.9425,
                    "gps_longitude": -118.4081,
                    "gps_accuracy_meters": 10.5,
                    "exif_device_make": "Apple",
                    "exif_device_model": "iPhone 14 Pro",
                    "is_tampered": False
                },
                "created_at": "2026-09-28T10:00:00"
            },
            "language": "en"
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _extract_exif_data(file_path: str) -> dict:
    """
    Extract EXIF metadata from image.
    Returns device info and timestamp.
    """
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        
        img = Image.open(file_path)
        exif_data = img._getexif() if hasattr(img, '_getexif') else None
        
        result = {
            "exif_device_make": None,
            "exif_device_model": None,
            "exif_timestamp": None,
            "width": img.width,
            "height": img.height,
        }
        
        if exif_data:
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, tag_id)
                
                if tag_name == "Make":
                    result["exif_device_make"] = str(value)[:100]
                elif tag_name == "Model":
                    result["exif_device_model"] = str(value)[:100]
                elif tag_name == "DateTime":
                    try:
                        result["exif_timestamp"] = datetime.strptime(
                            str(value), "%Y:%m:%d %H:%M:%S"
                        )
                    except (ValueError, TypeError):
                        pass
        
        return result
    except Exception as e:
        logger.warning("EXIF extraction failed: {}", e)
        return {
            "exif_device_make": None,
            "exif_device_model": None,
            "exif_timestamp": None,
            "width": None,
            "height": None,
        }


def _detect_image_quality(file_path: str) -> dict:
    """
    Simple image quality checks.
    Returns: {is_blurry, is_dark, quality_level}
    """
    try:
        from PIL import Image, ImageStat
        
        img = Image.open(file_path)
        
        # Convert to grayscale for analysis
        bw = img.convert('L')
        stat = ImageStat.Stat(bw)
        
        # Brightness (0=black, 255=white)
        brightness = stat.mean[0]
        is_dark = brightness < 50
        
        # Blurriness detection (edge sharpness)
        # Simple: low variance = blurry
        variance = stat.var[0] if stat.var else 0
        is_blurry = variance < 100
        
        # Quality assessment
        if is_dark or is_blurry:
            quality = "low"
        elif variance > 500:
            quality = "high"
        else:
            quality = "medium"
        
        return {
            "is_blurry": is_blurry,
            "is_dark": is_dark,
            "quality": quality,
        }
    except Exception as e:
        logger.warning("Quality detection failed: {}", e)
        return {
            "is_blurry": False,
            "is_dark": False,
            "quality": "medium",
        }


def _optimize_image(input_path: str, output_path: str, max_size: int = 1024) -> dict:
    """
    Optimize image: resize to max_size x max_size, JPEG 80%.
    Returns: {optimized_size_bytes, width, height}
    """
    try:
        from PIL import Image
        
        img = Image.open(input_path)
        
        # Resize maintaining aspect ratio
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # Save as JPEG 80%
        img.save(output_path, format='JPEG', quality=80, optimize=True)
        
        file_size = os.path.getsize(output_path)
        
        return {
            "optimized_size_bytes": file_size,
            "width": img.width,
            "height": img.height,
        }
    except Exception as e:
        logger.error("Image optimization failed: {}", e)
        raise


def _detect_tampering(exif_timestamp: Optional[datetime], local_timestamp: datetime) -> bool:
    """
    Detect possible tampering: EXIF timestamp vs local timestamp.
    Allow 5-minute difference for timezone drift.
    """
    if not exif_timestamp:
        return False
    
    time_diff = abs((exif_timestamp - local_timestamp).total_seconds())
    # More than 5 minutes difference = suspicious
    return time_diff > 300


def _to_detail(photo: InspectionPhoto) -> dict:
    """Convert model to detail response."""
    return {
        "id": photo.id,
        "rental_session_id": photo.rental_session_id,
        "angle_code": photo.angle_code.value,
        "angle_description": photo.angle_description,
        "original_filename": photo.original_filename,
        "local_uri": photo.local_uri,
        "cloud_uri": photo.cloud_uri,
        "timestamp": photo.timestamp,
        "image_quality": photo.image_quality,
        "is_blurry": photo.is_blurry,
        "is_dark": photo.is_dark,
        "upload_status": photo.upload_status.value,
        "metadata": {
            "timestamp": photo.timestamp,
            "gps_latitude": photo.gps_latitude,
            "gps_longitude": photo.gps_longitude,
            "gps_accuracy_meters": photo.gps_accuracy_meters,
            "exif_device_make": photo.exif_device_make,
            "exif_device_model": photo.exif_device_model,
            "is_tampered": photo.is_tampered,
        },
        "created_at": photo.created_at,
    }


def _to_summary(photo: InspectionPhoto) -> dict:
    """Convert model to summary response."""
    return {
        "id": photo.id,
        "angle_code": photo.angle_code.value,
        "upload_status": photo.upload_status.value,
        "image_quality": photo.image_quality,
        "is_blurry": photo.is_blurry,
        "is_dark": photo.is_dark,
        "created_at": photo.created_at,
    }


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/upload", response_model=PhotoUploadResponse, status_code=201)
async def upload_photo(
    request: Request,
    session_id: str = Form(..., description="Rental session ID"),
    angle_code: str = Form(..., description="Angle code (FRONT, REAR, LEFT, RIGHT, etc.)"),
    angle_description: Optional[str] = Form(None, description="Description"),
    gps_latitude: Optional[float] = Form(None, description="GPS latitude"),
    gps_longitude: Optional[float] = Form(None, description="GPS longitude"),
    gps_accuracy_meters: Optional[float] = Form(None, description="GPS accuracy"),
    file: UploadFile = File(..., description="Photo file"),
    db: Session = Depends(get_db),
):
    """
    Upload inspection photo with EXIF extraction and optimization.
    
    Automatically:
    - Extracts EXIF metadata (device, timestamp)
    - Optimizes image (1024x1024, JPEG 80%)
    - Detects quality issues (blur, darkness)
    - Detects tampering (EXIF timestamp vs local)
    - Creates sync queue entry for cloud upload
    """
    lang = get_language(request)
    
    try:
        logger.info("Photo upload: session={}, angle={}, file={}", 
                   session_id, angle_code, file.filename)
        
        # Validate session exists
        session = db.query(RentalSession).filter(
            RentalSession.id == session_id
        ).first()
        if not session:
            error_msg = get_text("error.sessionNotFound", language=lang)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        
        # Validate angle code
        try:
            angle_enum = AngleCodeEnum[angle_code.upper()]
        except KeyError:
            error_msg = get_text("error.invalidAngleCode", language=lang)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )
        
        # Create storage directory
        storage_dir = Path("/private/tmp/claude-502/-Users-evgenyz/5ea88836-9c90-4577-9ec8-def519a8478b/scratchpad/photos")
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique file ID
        photo_id = str(uuid.uuid4())
        local_filename = f"{photo_id}.jpg"
        local_path = storage_dir / local_filename
        
        # Save uploaded file temporarily
        contents = await file.read()
        with open(local_path, "wb") as f:
            f.write(contents)
        
        # Extract EXIF data
        exif_data = _extract_exif_data(str(local_path))
        logger.info("✓ EXIF extracted: device={} {}", 
                   exif_data.get("exif_device_make"),
                   exif_data.get("exif_device_model"))
        
        # Detect quality issues
        quality_data = _detect_image_quality(str(local_path))
        logger.info("✓ Quality analysis: quality={}, blurry={}, dark={}", 
                   quality_data["quality"],
                   quality_data["is_blurry"],
                   quality_data["is_dark"])
        
        # Optimize image
        optimized_path = storage_dir / f"{photo_id}_optimized.jpg"
        opt_data = _optimize_image(str(local_path), str(optimized_path))
        logger.info("✓ Image optimized: {}x{}, {} bytes",
                   opt_data["width"],
                   opt_data["height"],
                   opt_data["optimized_size_bytes"])
        
        # Detect tampering
        now = datetime.utcnow()
        is_tampered = _detect_tampering(exif_data.get("exif_timestamp"), now)
        if is_tampered:
            logger.warning("⚠ Tampering detected: EXIF timestamp mismatch")
        
        # Create photo record
        photo = InspectionPhoto(
            id=photo_id,
            rental_session_id=session_id,
            angle_code=angle_enum,
            angle_description=angle_description,
            original_filename=file.filename,
            local_uri=f"file://{local_path}",
            timestamp=now,
            gps_latitude=gps_latitude,
            gps_longitude=gps_longitude,
            gps_accuracy_meters=gps_accuracy_meters,
            original_size_bytes=len(contents),
            optimized_size_bytes=opt_data["optimized_size_bytes"],
            width=opt_data["width"],
            height=opt_data["height"],
            image_quality=quality_data["quality"],
            is_blurry=quality_data["is_blurry"],
            is_dark=quality_data["is_dark"],
            exif_device_make=exif_data.get("exif_device_make"),
            exif_device_model=exif_data.get("exif_device_model"),
            exif_timestamp=exif_data.get("exif_timestamp"),
            is_tampered=is_tampered,
            upload_status=UploadStatusEnum.PENDING,
        )
        db.add(photo)
        db.flush()  # Get photo ID
        
        # Create sync queue entry
        sync_item = SyncQueueItem(
            user_id=session.car_profile.user_id,
            entity_type="photo",
            entity_id=photo.id,
            action=SyncQueueActionEnum.CREATE,
            payload={
                "photo_id": photo.id,
                "session_id": session_id,
                "angle_code": angle_code,
                "local_uri": f"file://{local_path}",
            }
        )
        db.add(sync_item)
        db.commit()
        db.refresh(photo)
        
        logger.info("✓ Photo created: {} ({})", photo.id, angle_code)
        
        success_msg = get_text("common.success", language=lang)
        return PhotoUploadResponse(
            success=True,
            message=success_msg,
            data=_to_detail(photo),
            language=lang,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Photo upload error: {}", e, exc_info=True)
        error_msg = get_text("error.uploadFailed", language=lang)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )


@router.get("/sessions/{session_id}/photos", response_model=PhotoListResponse)
async def list_session_photos(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    List all photos for a rental session.
    Shows upload progress and quality assessments.
    """
    lang = get_language(request)
    
    try:
        logger.info("List photos: session={}", session_id)
        
        # Validate session exists
        session = db.query(RentalSession).filter(
            RentalSession.id == session_id
        ).first()
        if not session:
            error_msg = get_text("error.sessionNotFound", language=lang)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        
        # Get all photos for session
        photos = db.query(InspectionPhoto).filter(
            InspectionPhoto.rental_session_id == session_id
        ).order_by(InspectionPhoto.created_at.desc()).all()
        
        logger.info("✓ Found {} photos", len(photos))
        
        success_msg = get_text("common.success", language=lang)
        return PhotoListResponse(
            success=True,
            message=success_msg,
            data={
                "photos": [_to_summary(p) for p in photos],
                "count": len(photos),
                "session_id": session_id,
            },
            language=lang,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("List photos error: {}", e, exc_info=True)
        error_msg = get_text("error.fetchFailed", language=lang)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )


@router.get("/{photo_id}", response_model=PhotoUploadResponse)
async def get_photo(
    photo_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get detailed photo information."""
    lang = get_language(request)
    
    try:
        photo = db.query(InspectionPhoto).filter(
            InspectionPhoto.id == photo_id
        ).first()
        
        if not photo:
            error_msg = get_text("error.photoNotFound", language=lang)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        
        success_msg = get_text("common.success", language=lang)
        return PhotoUploadResponse(
            success=True,
            message=success_msg,
            data=_to_detail(photo),
            language=lang,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Get photo error: {}", e, exc_info=True)
        error_msg = get_text("error.fetchFailed", language=lang)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )


@router.delete("/{photo_id}", status_code=204)
async def delete_photo(
    photo_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete a photo (removes from storage and database)."""
    lang = get_language(request)
    
    try:
        photo = db.query(InspectionPhoto).filter(
            InspectionPhoto.id == photo_id
        ).first()
        
        if not photo:
            error_msg = get_text("error.photoNotFound", language=lang)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )
        
        # Delete local files
        try:
            local_path = Path(photo.local_uri.replace("file://", ""))
            if local_path.exists():
                local_path.unlink()
        except Exception as e:
            logger.warning("Failed to delete local file: {}", e)
        
        # Delete optimized file
        try:
            opt_path = local_path.parent / f"{photo_id}_optimized.jpg"
            if opt_path.exists():
                opt_path.unlink()
        except Exception as e:
            logger.warning("Failed to delete optimized file: {}", e)
        
        # Delete from database (cascade will clean sync queue)
        db.delete(photo)
        db.commit()
        
        logger.info("✓ Photo deleted: {}", photo_id)
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete photo error: {}", e, exc_info=True)
        error_msg = get_text("error.deleteFailed", language=lang)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )
