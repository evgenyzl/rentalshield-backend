"""
FastAPI middleware for language negotiation.

Supports:
1. Accept-Language header
2. Query parameter: ?lang=en
3. User preference (stored in database)
4. Falls back to DEFAULT_LANGUAGE
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable

from rentalshield.i18n import SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE


class LanguageMiddleware(BaseHTTPMiddleware):
    """
    Extract and validate user's language preference.
    Stores in request.state.language for use in route handlers.
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> any:

        # Priority 1: Query parameter (?lang=en)
        language = request.query_params.get("lang", "").lower()

        # Priority 2: Accept-Language header
        if not language:
            accept_language = request.headers.get("accept-language", "")
            if accept_language:
                # Parse "en-US,en;q=0.9,es;q=0.8" → get first language code
                language = accept_language.split(",")[0].split("-")[0].lower()

        # Priority 3: Cookie (if user set preference)
        if not language:
            language = request.cookies.get("language", "").lower()

        # Priority 4: Default
        if not language:
            language = DEFAULT_LANGUAGE

        # Validate language
        if language not in SUPPORTED_LANGUAGES:
            language = DEFAULT_LANGUAGE

        # Store in request state for use in route handlers
        request.state.language = language
        request.state.supported_languages = SUPPORTED_LANGUAGES
        request.state.default_language = DEFAULT_LANGUAGE

        # Call next middleware/route handler
        response = await call_next(request)

        # Set language cookie (24-hour expiry)
        response.set_cookie(
            "language",
            language,
            max_age=86400,
            path="/",
            httponly=True,
            samesite="lax",
        )

        return response


def get_language(request: Request) -> str:
    """
    Get current language from request.
    Usage in route handlers:
        def get_profile(request: Request):
            lang = get_language(request)
            text = get_text("dashboard.welcome", language=lang)
    """
    return getattr(request.state, "language", DEFAULT_LANGUAGE)
