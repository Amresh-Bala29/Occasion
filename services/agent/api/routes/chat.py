"""Chat routes — stream turns between the user and the agent team."""

from fastapi import APIRouter

router = APIRouter()


@router.post("")
async def chat(payload: dict) -> dict:
    return {"reply": "stub"}
