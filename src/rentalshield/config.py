"""
Settings loaded from environment variables / .env file.
All tunable knobs live here — nothing hardcoded in other modules.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent.parent
load_dotenv(_ROOT / ".env", override=False)


class Settings:
    # ── AI provider ──────────────────────────────────────────────────────────
    # "gemini"  → free tier, no credit card needed
    # "claude"  → Anthropic paid API
    ai_provider: str = os.environ.get("RENTALSHIELD_AI_PROVIDER", "gemini")

    # ── Gemini ───────────────────────────────────────────────────────────────
    gemini_api_key: str = os.environ.get("GEMINI_API_KEY", "")
    gemini_model:        str = os.environ.get("RENTALSHIELD_GEMINI_MODEL",
                                              "gemini-3.5-flash")
    # Lighter model for text-only tasks (PDF parsing, comparison)
    # Separate quota from the vision model so compare never blocks on scan limits
    gemini_text_model:   str = os.environ.get("RENTALSHIELD_GEMINI_TEXT_MODEL",
                                              "gemini-3.5-flash-lite")

    # ── Claude (fallback / paid) ──────────────────────────────────────────────
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    claude_model:      str = os.environ.get("RENTALSHIELD_CLAUDE_MODEL",
                                            "claude-opus-4-5")
    claude_max_tokens: int = 1024

    # ── Video analysis ────────────────────────────────────────────────────────
    frame_interval_s: float = float(
        os.environ.get("RENTALSHIELD_FRAME_INTERVAL_S", "3")
    )

    # ── Paths ─────────────────────────────────────────────────────────────────
    project_root: Path = _ROOT
    data_dir:     Path = _ROOT / "data"
    input_dir:    Path = _ROOT / "data" / "input"
    output_dir:   Path = _ROOT / "data" / "output"
    videos_dir:   Path = _ROOT / "data" / "input" / "videos"
    reports_dir:  Path = _ROOT / "data" / "input" / "company_reports"
    sessions_dir: Path = _ROOT / "data" / "output" / "sessions"
    crops_dir:    Path = _ROOT / "data" / "output" / "crops"

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = os.environ.get("RENTALSHIELD_LOG_LEVEL", "INFO")

    def ensure_dirs(self) -> None:
        for d in (self.sessions_dir, self.crops_dir):
            d.mkdir(parents=True, exist_ok=True)

    def validate(self) -> None:
        provider = self.ai_provider.lower()
        if provider == "gemini" and not self.gemini_api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set.\n"
                "Get a FREE key at https://aistudio.google.com/app/apikey\n"
                "then add it to your .env file."
            )
        if provider == "claude" and not self.anthropic_api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set.\n"
                "Copy .env.example → .env and add your key."
            )


settings = Settings()
