"""Event CRUD and planning-trigger routes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_events() -> list[dict]:
    return []


@router.post("")
async def create_event(payload: dict) -> dict:
    return {"id": "evt_stub", **payload}
