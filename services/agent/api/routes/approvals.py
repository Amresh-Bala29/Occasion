"""Approval routes — list and resolve pending approvals, executing what approval unlocks."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_event_repository, get_run_manager
from core.runs import RunManager
from database.repositories.event_repository import EventRepository
from models import web

router = APIRouter()


class ResolveApprovalBody(BaseModel):
    approved: bool


@router.get("", response_model=list[web.PendingApproval], response_model_exclude_none=True)
def list_approvals(repo: EventRepository = Depends(get_event_repository)) -> list[web.PendingApproval]:
    return repo.list_pending_approvals()


@router.post("/{approval_id}", response_model=web.DecisionRecord)
def resolve_approval(
    approval_id: str,
    body: ResolveApprovalBody,
    repo: EventRepository = Depends(get_event_repository),
    runs: RunManager = Depends(get_run_manager),
) -> web.DecisionRecord:
    # Records the decision and an activity line, and drops the approval from the
    # pending list. Returns the created decision for the "Recent decisions" panel.
    action = repo.get_approval_action(approval_id)  # read before resolve flips the row
    decision = repo.resolve_approval(approval_id, body.approved)
    if decision is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id!r} not found or already resolved")
    if body.approved and action is not None:
        # The approve click IS the go-ahead: execute what the row was asking for.
        runs.start_booking(action, approval_note=f"Approved in the dashboard (decision {decision.id}).")
    return decision
