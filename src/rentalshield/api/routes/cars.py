"""Car profile endpoints."""
from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def list_cars():
    """List user's car profiles (stub)."""
    return {"cars": []}
