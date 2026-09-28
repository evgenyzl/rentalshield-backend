"""Rental document endpoints."""
from fastapi import APIRouter

router = APIRouter()

@router.post("/upload")
async def upload_document():
    """Upload rental document for OCR (stub)."""
    return {"status": "not_implemented"}
