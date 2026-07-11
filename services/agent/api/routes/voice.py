"""Voice routes — speech-to-text and text-to-speech endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/transcribe")
async def transcribe() -> dict:
    return {"text": ""}
