"""
Phase 1 Settings loaded from environment variables / .env file.
All tunable knobs live here — nothing hardcoded in other modules.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent.parent
load_dotenv(_ROOT / ".env", override=False)


class Settings:
    # ── Environment ──────────────────────────────────────────────────────────
    environment: str = os.environ.get("RENTALSHIELD_ENV", "development")
    debug: bool = os.environ.get("RENTALSHIELD_DEBUG", "true").lower() in ("true", "1")
    api_port: int = int(os.environ.get("RENTALSHIELD_API_PORT", "8888"))

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "sqlite:///./rentalshield.db"
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:5173",
        "*",  # For testing
    ]

    # ── AI Providers (Phase 2) ────────────────────────────────────────────────
    ai_provider: str = os.environ.get("RENTALSHIELD_AI_PROVIDER", "gemini")

    # Gemini (for Phase 2: document OCR, damage detection)
    gemini_api_key: str = os.environ.get("GEMINI_API_KEY", "")
    gemini_model: str = os.environ.get("RENTALSHIELD_GEMINI_MODEL", "gemini-2.0-flash")

    # Claude (fallback / paid)
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    claude_model: str = os.environ.get("RENTALSHIELD_CLAUDE_MODEL", "claude-opus-5")

    # ── Cloud Storage (Phase 2) ───────────────────────────────────────────────
    storage_provider: str = os.environ.get("RENTALSHIELD_STORAGE", "local")  # local, s3, gcs
    aws_access_key_id: str = os.environ.get("AWS_ACCESS_KEY_ID", "")
    aws_secret_access_key: str = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    aws_s3_bucket: str = os.environ.get("AWS_S3_BUCKET", "rentalshield-photos")
    gcs_bucket: str = os.environ.get("GCS_BUCKET", "rentalshield-photos")

    # ── Firebase (Authentication - Phase 2) ───────────────────────────────────
    firebase_project_id: str = os.environ.get("FIREBASE_PROJECT_ID", "")
    firebase_private_key: str = os.environ.get("FIREBASE_PRIVATE_KEY", "")
    firebase_client_email: str = os.environ.get("FIREBASE_CLIENT_EMAIL", "")

    # ── Paths ─────────────────────────────────────────────────────────────────
    project_root: Path = _ROOT
    data_dir: Path = _ROOT / "data"
    photos_dir: Path = _ROOT / "data" / "photos"
    reports_dir: Path = _ROOT / "data" / "reports"

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = os.environ.get("RENTALSHIELD_LOG_LEVEL", "INFO")

    def ensure_dirs(self) -> None:
        """Create required directories."""
        for d in (self.photos_dir, self.reports_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
