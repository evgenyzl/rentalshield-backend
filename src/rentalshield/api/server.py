"""
FastAPI application factory and middleware setup.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from loguru import logger
import time

from rentalshield.config import settings
from rentalshield.db.database import init_db, verify_db_connection
from rentalshield.i18n.middleware import LanguageMiddleware


# ============================================================================
# LIFESPAN EVENTS
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handlers (startup and shutdown).
    """
    # STARTUP
    logger.info("=" * 60)
    logger.info("🚀 RentalShield Phase 1 Starting Up")
    logger.info("=" * 60)
    logger.info("Environment: {}", settings.environment)
    logger.info("Debug: {}", settings.debug)
    logger.info("API URL: http://localhost:{}", settings.api_port)

    # Initialize database
    try:
        init_db()
        verify_db_connection()
        logger.info("✓ Database initialized")
    except Exception as e:
        logger.error("✗ Database initialization failed: {}", e)
        raise

    yield

    # SHUTDOWN
    logger.info("🛑 RentalShield Shutting Down")


# ============================================================================
# FASTAPI APP FACTORY
# ============================================================================

def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    app = FastAPI(
        title="RentalShield API",
        description="Car rental inspection and damage documentation",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ========================================================================
    # MIDDLEWARE
    # ========================================================================

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Language middleware (must be after CORS)
    app.add_middleware(LanguageMiddleware)

    # ========================================================================
    # EXCEPTION HANDLERS
    # ========================================================================

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        """Catch-all exception handler."""
        logger.error("Unhandled exception: {}", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": str(exc) if settings.debug else "An error occurred",
            },
        )

    # ========================================================================
    # HEALTH CHECK ENDPOINTS
    # ========================================================================

    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "version": "1.0.0",
        }

    @app.get("/ready", tags=["Health"])
    async def ready_check():
        """Readiness check (db + dependencies)."""
        from rentalshield.db.database import verify_db_connection

        db_ok = verify_db_connection()
        if not db_ok:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "reason": "database_unavailable"},
            )
        return {"status": "ready"}

    # ========================================================================
    # INFO ENDPOINTS
    # ========================================================================

    @app.get("/config", tags=["Info"])
    async def get_config(request):
        """Get app configuration (public info only)."""
        from rentalshield.i18n import list_languages, SUPPORTED_LANGUAGES
        from rentalshield.i18n.middleware import get_language

        lang = get_language(request)
        return {
            "app": {
                "name": "RentalShield",
                "version": "1.0.0",
                "environment": settings.environment,
            },
            "languages": {
                "supported": SUPPORTED_LANGUAGES,
                "current": lang,
                "names": list_languages(),
            },
            "features": {
                "document_parsing": True,
                "photo_capture": True,
                "offline_mode": True,
                "phase2_ai": False,  # Coming soon
            },
        }

    # ========================================================================
    # INCLUDE ROUTERS
    # ========================================================================

    # Import and include routers
    from rentalshield.api.routes.auth import router as auth_router
    from rentalshield.api.routes.users import router as users_router
    from rentalshield.api.routes.cars import router as cars_router
    from rentalshield.api.routes.sessions import router as sessions_router
    from rentalshield.api.routes.photos import router as photos_router
    from rentalshield.api.routes.documents import router as documents_router
    from rentalshield.api.routes.reports import router as reports_router

    app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(users_router, prefix="/api/v1/users", tags=["Users"])
    app.include_router(cars_router, prefix="/api/v1/cars", tags=["Car Profiles"])
    app.include_router(sessions_router, prefix="/api/v1/sessions", tags=["Rental Sessions"])
    app.include_router(photos_router, prefix="/api/v1/photos", tags=["Inspection Photos"])
    app.include_router(documents_router, prefix="/api/v1/documents", tags=["Rental Documents"])
    app.include_router(reports_router, prefix="/api/v1/reports", tags=["Reports"])

    logger.info("✓ All routers registered")

    return app


# ============================================================================
# CREATE APP INSTANCE
# ============================================================================

app = create_app()
