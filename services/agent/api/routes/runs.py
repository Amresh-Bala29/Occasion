"""Run routes — poll a background agent run until it settles."""

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_run_repository
from database.repositories.run_repository import RunRecord, RunRepository

router = APIRouter()


@router.get("", response_model=list[RunRecord], response_model_exclude_none=True)
def list_runs(
    event_id: str, kind: str | None = None, repo: RunRepository = Depends(get_run_repository)
) -> list[RunRecord]:
    """One event's runs, oldest first — the durable chat log the web app rebuilds
    its thread from. `event_id` is required so there is no accidental full dump."""
    return repo.list_for_event(event_id, kind=kind)


@router.get("/{run_id}", response_model=RunRecord, response_model_exclude_none=True)
def get_run(run_id: str, repo: RunRepository = Depends(get_run_repository)) -> RunRecord:
    record = repo.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return record
