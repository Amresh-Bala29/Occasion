"""Chat routes — turn one user message into a background orchestrated run."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.dependencies import get_run_manager
from core.runs import RunManager
from database.repositories.run_repository import RunRecord

router = APIRouter()


class ChatRequest(BaseModel):
    """One user turn. With event_id the message runs as an event-scoped Task;
    without it, as a plain string (workflows then decline, by design)."""

    message: str = Field(..., min_length=1)
    event_id: str | None = None
    # Pins the run to one fleet member (the intake page pins "requirements"),
    # skipping the router. Rides on the Task, so it needs event_id to take effect.
    agent: str | None = None


@router.post("", response_model=RunRecord)
async def chat(request: ChatRequest, runs: RunManager = Depends(get_run_manager)) -> RunRecord:
    """Start the run and return its `running` record immediately.

    The orchestrator routes and executes in the background — browser sessions can
    take minutes — so clients poll GET /runs/{id} until the record settles.
    Routing and agent failures land inside the settled record, never as HTTP errors.
    """
    return runs.start_chat(request.message, request.event_id, agent=request.agent)
