"""User profile endpoints."""
from fastapi import APIRouter

router = APIRouter()

@router.get("/profile")
async def get_profile():
    """Get user profile (stub)."""
    return {"status": "not_implemented"}
