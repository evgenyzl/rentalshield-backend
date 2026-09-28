"""
Authentication endpoints.
Firebase integration for user login/signup.
"""

from fastapi import APIRouter, Request, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr, Field
from loguru import logger

from rentalshield.i18n import get_text
from rentalshield.i18n.middleware import get_language
from rentalshield.db.database import get_db
from rentalshield.db.models import User
from sqlalchemy.orm import Session

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class SignUpRequest(BaseModel):
    """Sign up request model."""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=6, description="Password (min 6 chars)")
    display_name: str = Field(..., min_length=1, description="Display name")
    language: str = Field(default="en", description="Preferred language (en, it, es, fr)")

    class Config:
        example = {
            "email": "john@example.com",
            "password": "securepassword123",
            "display_name": "John Doe",
            "language": "en",
        }


class LoginRequest(BaseModel):
    """Login request model."""
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="Password")

    class Config:
        example = {
            "email": "john@example.com",
            "password": "securepassword123",
        }


class AuthResponse(BaseModel):
    """Authentication response."""
    success: bool = Field(..., description="Success status")
    message: str = Field(..., description="Status message")
    user: dict = Field(None, description="User data")
    token: str = Field(None, description="Auth token")
    language: str = Field(..., description="User's language")

    class Config:
        example = {
            "success": True,
            "message": "Login successful",
            "user": {
                "id": "uuid",
                "email": "john@example.com",
                "display_name": "John Doe",
            },
            "token": "eyJhbGciOiJIUzI1NiIs...",
            "language": "en",
        }


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/signup", response_model=AuthResponse)
async def sign_up(
    request: Request,
    payload: SignUpRequest,
    db: Session = Depends(get_db),
):
    """
    Create a new user account.
    Integrates with Firebase for authentication.
    """
    lang = get_language(request)

    try:
        logger.info("Sign up attempt: {}", payload.email)

        # Check if user already exists
        existing_user = db.query(User).filter(User.email == payload.email).first()
        if existing_user:
            error_msg = get_text("auth.loginFailed", language=lang)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )

        # TODO: Integrate Firebase Authentication
        # firebase_user = firebase_auth.create_user(
        #     email=payload.email,
        #     password=payload.password,
        #     display_name=payload.display_name
        # )

        # Create user in database
        new_user = User(
            firebase_uid="temp_uid",  # TODO: Use Firebase UID
            email=payload.email,
            display_name=payload.display_name,
            language=payload.language,
            is_email_verified=False,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info("✓ User created: {}", payload.email)

        success_msg = get_text("common.success", language=lang)
        return AuthResponse(
            success=True,
            message=success_msg,
            user={
                "id": new_user.id,
                "email": new_user.email,
                "display_name": new_user.display_name,
            },
            token="temp_token",  # TODO: Generate JWT token
            language=lang,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Sign up error: {}", e, exc_info=True)
        error_msg = get_text("auth.signupFailed", language=lang)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: Request,
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Authenticate user with email and password.
    Returns JWT token for subsequent requests.
    """
    lang = get_language(request)

    try:
        logger.info("Login attempt: {}", payload.email)

        # Get user from database
        user = db.query(User).filter(User.email == payload.email).first()
        if not user:
            error_msg = get_text("auth.loginFailed", language=lang)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_msg,
            )

        # TODO: Verify password with Firebase
        # firebase_user = firebase_auth.get_user_by_email(payload.email)
        # firebase_auth.verify_password(firebase_user, payload.password)

        # Update last login
        from datetime import datetime
        user.last_login_at = datetime.utcnow()
        db.commit()
        db.refresh(user)

        logger.info("✓ User logged in: {}", payload.email)

        success_msg = get_text("common.success", language=lang)
        return AuthResponse(
            success=True,
            message=success_msg,
            user={
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
            },
            token="temp_token",  # TODO: Generate JWT token
            language=user.language,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login error: {}", e, exc_info=True)
        error_msg = get_text("auth.loginFailed", language=lang)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg,
        )


@router.post("/logout")
async def logout(request: Request):
    """Logout user (client-side token invalidation)."""
    lang = get_language(request)
    success_msg = get_text("common.success", language=lang)

    return {
        "success": True,
        "message": success_msg,
        "language": lang,
    }


@router.get("/me")
async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
):
    """Get current authenticated user."""
    lang = get_language(request)

    # TODO: Extract user ID from JWT token
    user_id = "temp_user_id"

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "language": user.language,
        "created_at": user.created_at,
        "language": lang,
    }
