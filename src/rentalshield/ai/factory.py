"""
AI provider factory.
Returns the configured analyzer based on RENTALSHIELD_AI_PROVIDER in .env.
Default: gemini (free tier).
"""

from __future__ import annotations

from rentalshield.config import settings
from rentalshield.ai.base import BaseAnalyzer


def get_analyzer() -> BaseAnalyzer:
    provider = settings.ai_provider.lower()

    if provider == "gemini":
        from rentalshield.ai.gemini_analyzer import GeminiAnalyzer
        return GeminiAnalyzer()

    if provider == "claude":
        from rentalshield.ai.analyzer import DamageAnalyzer
        return DamageAnalyzer()

    raise ValueError(
        f"Unknown AI provider: '{provider}'. "
        "Set RENTALSHIELD_AI_PROVIDER=gemini or claude in .env"
    )
