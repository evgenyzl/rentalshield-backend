"""
SQLAlchemy database models for RentalShield Phase 1.
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    Text, JSON, ForeignKey, Enum, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum
import uuid

Base = declarative_base()


def generate_id():
    """Generate UUID for database records."""
    return str(uuid.uuid4())


# ============================================================================
# USER MODEL
# ============================================================================

class User(Base):
    """User account (Firebase Auth integration)."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_id)
    firebase_uid = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    phone_number = Column(String(20), nullable=True)
    profile_picture_url = Column(String(500), nullable=True)

    # Preferences
    language = Column(String(5), default="en")  # en, it, es, fr
    timezone = Column(String(50), default="UTC")
    enable_notifications = Column(Boolean, default=True)
    enable_email_notifications = Column(Boolean, default=True)

    # Account status
    is_active = Column(Boolean, default=True)
    is_email_verified = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    # Relations
    car_profiles = relationship("CarProfile", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_users_firebase_uid", "firebase_uid"),
        Index("idx_users_email", "email"),
    )


# ============================================================================
# CAR PROFILE MODEL
# ============================================================================

class CarProfile(Base):
    """Rental vehicle profile (auto-populated from rental document)."""
    __tablename__ = "car_profiles"

    id = Column(String(36), primary_key=True, default=generate_id)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Auto-populated from rental document
    rental_provider = Column(String(255), nullable=True)  # e.g., "Hertz", "Sixt"
    make = Column(String(100), nullable=True)  # e.g., "Ford"
    model = Column(String(100), nullable=True)  # e.g., "Focus"
    year = Column(Integer, nullable=True)  # e.g., 2023
    license_plate = Column(String(50), nullable=False, index=True)
    vin = Column(String(50), nullable=True)  # Vehicle Identification Number
    color = Column(String(50), nullable=True)  # e.g., "Silver"
    mileage_at_pickup = Column(Integer, nullable=True)
    photo_url = Column(String(500), nullable=True)  # Car photo URL

    # Rental timeline
    rental_start_date = Column(DateTime, nullable=False)
    rental_end_date = Column(DateTime, nullable=False)
    pickup_location = Column(String(255), nullable=True)  # e.g., "LAX Terminal 3"
    dropoff_location = Column(String(255), nullable=True)

    # Status
    status = Column(String(20), default="active")  # active, completed, disputed

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    user = relationship("User", back_populates="car_profiles")
    rental_sessions = relationship("RentalSession", back_populates="car_profile", cascade="all, delete-orphan")
    rental_documents = relationship("RentalDocument", back_populates="car_profile", cascade="all, delete-orphan")
    dispute_reports = relationship("DisputeReport", back_populates="car_profile", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_car_profiles_user_id", "user_id"),
        Index("idx_car_profiles_license_plate", "license_plate"),
        Index("idx_car_profiles_status", "status"),
    )


# ============================================================================
# RENTAL SESSION MODEL (Pickup/Dropoff Inspection)
# ============================================================================

class SessionTypeEnum(str, enum.Enum):
    """Session type enumeration."""
    PICKUP = "pickup"
    DROPOFF = "dropoff"
    INTERIM_CHECK = "interim_check"


class SyncStatusEnum(str, enum.Enum):
    """Sync status enumeration."""
    PENDING = "pending"
    SYNCING = "syncing"
    SYNCED = "synced"
    ERROR = "error"


class RentalSession(Base):
    """Pickup or dropoff inspection event."""
    __tablename__ = "rental_sessions"

    id = Column(String(36), primary_key=True, default=generate_id)
    car_profile_id = Column(String(36), ForeignKey("car_profiles.id"), nullable=False, index=True)

    # Session type
    session_type = Column(Enum(SessionTypeEnum), nullable=False)

    # Time & location
    timestamp = Column(DateTime, nullable=False)
    gps_latitude = Column(Float, nullable=True)
    gps_longitude = Column(Float, nullable=True)
    gps_accuracy_meters = Column(Float, nullable=True)
    gps_address = Column(String(255), nullable=True)

    # Pre-existing damages (JSON array)
    pre_existing_damages = Column(JSON, nullable=True)  # [{location, description, severity}, ...]

    # Session completion
    is_complete = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)

    # Sync status
    sync_status = Column(Enum(SyncStatusEnum), default=SyncStatusEnum.PENDING)
    sync_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    car_profile = relationship("CarProfile", back_populates="rental_sessions")
    inspection_photos = relationship("InspectionPhoto", back_populates="rental_session", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_rental_sessions_car_profile_id", "car_profile_id"),
        Index("idx_rental_sessions_session_type", "session_type"),
        Index("idx_rental_sessions_sync_status", "sync_status"),
    )


# ============================================================================
# INSPECTION PHOTO MODEL (8 angles per session)
# ============================================================================

class AngleCodeEnum(str, enum.Enum):
    """Photo angle codes."""
    FRONT = "FRONT"
    REAR = "REAR"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    FRONT_DETAIL = "FRONT_DETAIL"
    REAR_DETAIL = "REAR_DETAIL"
    LEFT_DETAIL = "LEFT_DETAIL"
    RIGHT_DETAIL = "RIGHT_DETAIL"


class UploadStatusEnum(str, enum.Enum):
    """Upload status enumeration."""
    PENDING = "pending"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    ERROR = "error"


class InspectionPhoto(Base):
    """Photo evidence (one of 8 angles per session)."""
    __tablename__ = "inspection_photos"

    id = Column(String(36), primary_key=True, default=generate_id)
    rental_session_id = Column(String(36), ForeignKey("rental_sessions.id"), nullable=False, index=True)

    # Angle & metadata
    angle_code = Column(Enum(AngleCodeEnum), nullable=False)
    angle_description = Column(String(255), nullable=True)  # e.g., "Front bumper - full view"

    # File metadata
    original_filename = Column(String(255), nullable=False)
    local_uri = Column(String(500), nullable=False)  # file:// URI
    cloud_uri = Column(String(500), nullable=True)  # s3:// or gs:// URI

    # Immutable metadata (set at capture, never changed)
    timestamp = Column(DateTime, nullable=False)
    gps_latitude = Column(Float, nullable=True)
    gps_longitude = Column(Float, nullable=True)
    gps_accuracy_meters = Column(Float, nullable=True)

    # Image data
    original_size_bytes = Column(Integer, nullable=True)
    optimized_size_bytes = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)  # Original width
    height = Column(Integer, nullable=True)  # Original height

    # Quality & processing
    image_quality = Column(String(20), default="medium")  # high, medium, low
    is_blurry = Column(Boolean, default=False)
    is_dark = Column(Boolean, default=False)

    # EXIF data (tamper detection)
    exif_device_make = Column(String(100), nullable=True)  # e.g., "Apple"
    exif_device_model = Column(String(100), nullable=True)  # e.g., "iPhone 14 Pro"
    exif_timestamp = Column(DateTime, nullable=True)  # From EXIF
    is_tampered = Column(Boolean, default=False)  # Mismatch with local timestamp?

    # Sync & status
    upload_status = Column(Enum(UploadStatusEnum), default=UploadStatusEnum.PENDING)
    upload_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    rental_session = relationship("RentalSession", back_populates="inspection_photos")

    __table_args__ = (
        Index("idx_inspection_photos_rental_session_id", "rental_session_id"),
        Index("idx_inspection_photos_angle_code", "angle_code"),
        Index("idx_inspection_photos_upload_status", "upload_status"),
    )


# ============================================================================
# RENTAL DOCUMENT MODEL (PDFs, contract scans)
# ============================================================================

class DocumentTypeEnum(str, enum.Enum):
    """Document type enumeration."""
    RENTAL_CONTRACT = "rental_contract"
    CHECKOUT_FORM = "checkout_form"
    INSURANCE = "insurance"
    OTHER = "other"


class RentalDocument(Base):
    """Rental contract or inspection document."""
    __tablename__ = "rental_documents"

    id = Column(String(36), primary_key=True, default=generate_id)
    car_profile_id = Column(String(36), ForeignKey("car_profiles.id"), nullable=False, index=True)

    document_type = Column(Enum(DocumentTypeEnum), nullable=False)

    # File metadata
    original_filename = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String(50), nullable=True)  # "application/pdf", "image/jpeg"
    local_uri = Column(String(500), nullable=False)  # Offline storage path
    cloud_uri = Column(String(500), nullable=True)

    # Extracted data (from OCR/parsing)
    extracted_data = Column(JSON, nullable=True)  # {rental_provider, car_make, car_model, etc.}

    # Quality & confidence
    ocr_confidence = Column(Float, default=0.0)  # 0.0 to 1.0
    needs_manual_review = Column(Boolean, default=False)

    # Sync status
    upload_status = Column(Enum(UploadStatusEnum), default=UploadStatusEnum.PENDING)
    uploaded_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    car_profile = relationship("CarProfile", back_populates="rental_documents")

    __table_args__ = (
        Index("idx_rental_documents_car_profile_id", "car_profile_id"),
        Index("idx_rental_documents_document_type", "document_type"),
        Index("idx_rental_documents_upload_status", "upload_status"),
    )


# ============================================================================
# DISPUTE REPORT MODEL (Generated PDFs)
# ============================================================================

class DisputeReport(Base):
    """Generated Inspection Passport PDF."""
    __tablename__ = "dispute_reports"

    id = Column(String(36), primary_key=True, default=generate_id)
    car_profile_id = Column(String(36), ForeignKey("car_profiles.id"), nullable=False, index=True)

    report_title = Column(String(255), nullable=True)

    # Report contents (structured JSON)
    sections = Column(JSON, nullable=True)  # Full report structure

    # Export state
    pdf_generated_at = Column(DateTime, nullable=True)
    pdf_uri = Column(String(500), nullable=True)  # file:// or s3://
    pdf_size_bytes = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    car_profile = relationship("CarProfile", back_populates="dispute_reports")

    __table_args__ = (
        Index("idx_dispute_reports_car_profile_id", "car_profile_id"),
    )


# ============================================================================
# SYNC QUEUE MODEL (Background uploads)
# ============================================================================

class SyncQueueActionEnum(str, enum.Enum):
    """Sync action enumeration."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class SyncQueueItem(Base):
    """Item in the sync queue for background processing."""
    __tablename__ = "sync_queue"

    id = Column(String(36), primary_key=True, default=generate_id)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    entity_type = Column(String(50), nullable=False)  # photo, document, session_metadata
    entity_id = Column(String(36), nullable=False)
    action = Column(Enum(SyncQueueActionEnum), nullable=False)  # create, update, delete
    payload = Column(JSON, nullable=False)  # Full data to sync

    retry_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_sync_queue_user_id", "user_id"),
        Index("idx_sync_queue_entity_type", "entity_type"),
    )
