"""Run routes — poll a background agent run until it settles."""

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_run_repository
from database.repositories.run_repository import RunRecord, RunRepository

router = APIRouter()


@router.get("/{run_id}", response_model=RunRecord, response_model_exclude_none=True)
def get_run(run_id: str, repo: RunRepository = Depends(get_run_repository)) -> RunRecord:
    record = repo.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return record
