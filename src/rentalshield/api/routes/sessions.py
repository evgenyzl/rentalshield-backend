"""Rental session endpoints."""
from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def list_sessions():
    """List rental sessions (stub)."""
    return {"sessions": []}
