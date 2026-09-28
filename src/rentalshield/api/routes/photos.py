"""Inspection photo endpoints."""
from fastapi import APIRouter

router = APIRouter()

@router.post("/upload")
async def upload_photo():
    """Upload inspection photo (stub)."""
    return {"status": "not_implemented"}
