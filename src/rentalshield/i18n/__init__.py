"""
Internationalization (i18n) support for RentalShield.

Supported languages:
- en: English
- it: Italiano
- es: Español
- fr: Français
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

# Supported languages
SUPPORTED_LANGUAGES = ["en", "it", "es", "fr"]
DEFAULT_LANGUAGE = "en"

# Load all translation files
_TRANSLATIONS: Dict[str, Dict[str, Any]] = {}
_TRANSLATIONS_DIR = Path(__file__).parent / "translations"

for lang in SUPPORTED_LANGUAGES:
    try:
        with open(_TRANSLATIONS_DIR / f"{lang}.json", "r", encoding="utf-8") as f:
            _TRANSLATIONS[lang] = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"Translation file not found: {lang}.json")


def get_text(key: str, language: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """
    Get translated text by key.

    Args:
        key: Dot-separated key path (e.g., "dashboard.welcome")
        language: Language code (en, it, es, fr)
        **kwargs: Variables to interpolate (e.g., name="John")

    Returns:
        Translated text with variables interpolated

    Example:
        get_text("dashboard.welcome", language="en", name="John")
        → "Welcome, John"
    """

    # Validate language
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    # Navigate nested dictionary
    parts = key.split(".")
    text = _TRANSLATIONS[language]

    for part in parts:
        if isinstance(text, dict) and part in text:
            text = text[part]
        else:
            # Key not found, return key itself as fallback
            return key

    # Interpolate variables using {{variable}} syntax
    if isinstance(text, str) and kwargs:
        for var, value in kwargs.items():
            text = text.replace(f"{{{{{var}}}}}", str(value))

    return text if isinstance(text, str) else str(text)


def get_language_name(language: str) -> str:
    """Get the display name of a language."""
    return get_text("common.language", language=language)


def list_languages() -> Dict[str, str]:
    """Get list of all supported languages with their display names."""
    return {lang: get_language_name(lang) for lang in SUPPORTED_LANGUAGES}


__all__ = [
    "SUPPORTED_LANGUAGES",
    "DEFAULT_LANGUAGE",
    "get_text",
    "get_language_name",
    "list_languages",
]
