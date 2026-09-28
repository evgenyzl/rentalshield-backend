"""
Database connection and session management.
"""

from sqlalchemy import create_engine, pool
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from typing import Generator
import os
from loguru import logger

from rentalshield.config import settings

# ============================================================================
# DATABASE URL
# ============================================================================

DATABASE_URL = settings.database_url or "sqlite:///./rentalshield.db"

logger.info("Database URL: {}", DATABASE_URL.split("@")[0] if "@" in DATABASE_URL else DATABASE_URL)

# ============================================================================
# ENGINE CONFIGURATION
# ============================================================================

if DATABASE_URL.startswith("sqlite"):
    # SQLite for development
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    # PostgreSQL for production
    engine = create_engine(
        DATABASE_URL,
        echo=settings.debug,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,   # Recycle connections after 1 hour
    )

# ============================================================================
# SESSION FACTORY
# ============================================================================

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for getting database session.

    Usage:
        @app.get("/items")
        async def get_items(db: Session = Depends(get_db)):
            items = db.query(Item).all()
            return items
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# UTILITIES
# ============================================================================

def init_db():
    """Initialize database tables."""
    from rentalshield.db.models import Base

    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("✓ Database tables created")


def drop_db():
    """Drop all database tables (caution!)."""
    from rentalshield.db.models import Base

    logger.warning("Dropping all database tables...")
    Base.metadata.drop_all(bind=engine)
    logger.warning("✓ All database tables dropped")


def verify_db_connection():
    """Verify database connection is working."""
    try:
        with SessionLocal() as db:
            db.execute("SELECT 1")
        logger.info("✓ Database connection verified")
        return True
    except Exception as e:
        logger.error("✗ Database connection failed: {}", e)
        return False
