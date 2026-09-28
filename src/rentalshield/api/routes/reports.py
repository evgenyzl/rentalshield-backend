"""Report generation endpoints."""
from fastapi import APIRouter

router = APIRouter()

@router.post("/generate")
async def generate_report():
    """Generate inspection passport PDF (stub)."""
    return {"status": "not_implemented"}
