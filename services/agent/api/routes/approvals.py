"""Approval routes — list and resolve pending approvals."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_event_repository
from database.repositories.event_repository import EventRepository
from models import web

router = APIRouter()


class ResolveApprovalBody(BaseModel):
    approved: bool


@router.get("")
async def list_approvals() -> list[dict]:
    return []


@router.post("/{approval_id}", response_model=web.DecisionRecord)
def resolve_approval(
    approval_id: str, body: ResolveApprovalBody, repo: EventRepository = Depends(get_event_repository)
) -> web.DecisionRecord:
    # Records the decision and an activity line, and drops the approval from the
    # pending list. Returns the created decision for the "Recent decisions" panel.
    decision = repo.resolve_approval(approval_id, body.approved)
    if decision is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id!r} not found or already resolved")
    return decision
