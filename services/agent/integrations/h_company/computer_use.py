"""Computer-use browser-task entry point.

Wires configured credentials to the H client and runs a single natural-language browser
task. This is the reusable seam other agents call to do real web work.
"""

from __future__ import annotations

from core.config import settings
from integrations.h_company.client import HClient
from integrations.h_company.schemas import ComputerUseRequest, SessionResult

# Client-side ceiling for one ad-hoc task (matches the orchestrator's built-in cap).
# Without it a stuck session pins its worker thread indefinitely.
MAX_TIME_S = 1200.0


def run_browser_task(request: ComputerUseRequest, client: HClient | None = None) -> SessionResult:
    """Run one browser task through the managed H agent and return the outcome.

    Blocking: the SDK runs the whole session server-side and returns once it settles, so
    async callers must offload this to a worker thread.
    """
    if not settings.hai_api_key:
        return SessionResult(
            succeeded=False,
            status="error",
            error="HAI_API_KEY is not configured; set it in services/agent/.env",
        )
    runner = client or HClient.from_settings()
    return runner.run_task(task=request.task, agent=request.agent, max_time_s=MAX_TIME_S)
