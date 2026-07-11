"""Inbound webhooks (email replies, distribution callbacks, payments)."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/{source}")
async def receive(source: str, payload: dict) -> dict:
    return {"source": source, "received": True}
