"""
Pydantic models for i18n responses.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class LocalizedString(BaseModel):
    """A string that can be displayed in multiple languages."""

    en: str = Field(..., description="English text")
    it: str = Field(..., description="Italian text")
    es: str = Field(..., description="Spanish text")
    fr: str = Field(..., description="French text")

    class Config:
        example = {
            "en": "Welcome, John",
            "it": "Benvenuto, Giovanni",
            "es": "Bienvenido, Juan",
            "fr": "Bienvenue, Jean",
        }


class LanguageListResponse(BaseModel):
    """Response listing all supported languages."""

    languages: Dict[str, str] = Field(
        ..., description="Mapping of language codes to display names"
    )
    current: str = Field(..., description="Current user's language")

    class Config:
        example = {
            "languages": {"en": "English", "it": "Italiano", "es": "Español", "fr": "Français"},
            "current": "en",
        }


class LocalizedError(BaseModel):
    """Error response with localized message."""

    error_code: str = Field(..., description="Machine-readable error code")
    message: LocalizedString = Field(..., description="Error message in all languages")
    details: Optional[Dict] = Field(None, description="Additional error details")

    class Config:
        example = {
            "error_code": "DOCUMENT_PARSE_ERROR",
            "message": {
                "en": "Failed to parse document",
                "it": "Errore nell'analisi del documento",
                "es": "Error al analizar el documento",
                "fr": "Erreur lors de l'analyse du document",
            },
            "details": {"file": "rental_contract.pdf"},
        }


class I18nConfig(BaseModel):
    """User's i18n configuration."""

    language: str = Field(..., description="Current language code")
    supported_languages: List[str] = Field(..., description="List of supported languages")
    auto_detect: bool = Field(
        default=True, description="Automatically detect language from browser/device"
    )

    class Config:
        example = {
            "language": "en",
            "supported_languages": ["en", "it", "es", "fr"],
            "auto_detect": True,
        }
