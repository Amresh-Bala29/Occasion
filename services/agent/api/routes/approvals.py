"""Approval routes — list and resolve pending approvals."""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_approvals() -> list[dict]:
    return []


@router.post("/{approval_id}")
async def resolve_approval(approval_id: str, payload: dict) -> dict:
    return {"id": approval_id, "resolved": True}
