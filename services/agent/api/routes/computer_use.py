"""Computer-use routes — run a managed H Company browser task."""

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from integrations.h_company.computer_use import run_browser_task
from integrations.h_company.schemas import ComputerUseRequest, SessionResult

router = APIRouter()


@router.post("/run", response_model=SessionResult)
async def run(request: ComputerUseRequest) -> SessionResult:
    """Run one natural-language browser task and report the honest outcome.

    The response carries the real run status (completed / failed / timed_out /
    interrupted / idle) and the agent's self-assessed outcome (success / partial /
    infeasible / blocked), plus the answer, any error, the session id, and the Agent
    View URL when available. Session failures come back with succeeded=False, not raised.
    """
    # run_session blocks until the session settles; keep the event loop free.
    return await run_in_threadpool(run_browser_task, request)
