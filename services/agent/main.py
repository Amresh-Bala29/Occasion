"""Occasion agent service — FastAPI entry point."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import approvals, chat, computer_use, events, runs, voice, webhooks
from core.logging import configure_logging
from core.runs import run_manager
from database.connection import dispose, new_session
from database.repositories.run_repository import RunRepository

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Sync route handlers start background runs from threadpool threads; they need
    # the loop captured here.
    run_manager.bind(asyncio.get_running_loop())
    _sweep_stale_runs()
    # The sweep marks dead-process runs interrupted; recovery then republishes what
    # their finished H sessions and memory snapshots still hold.
    run_manager.start_recovery()
    yield
    # Connections are validated per-checkout (pool_pre_ping); just tear the pool
    # down cleanly on shutdown.
    dispose()


def _sweep_stale_runs() -> None:
    """Runs a dead process left `running` can never settle; mark them interrupted.

    Best-effort: the service must still boot (health, computer-use) with no
    database configured, so a failed sweep logs instead of raising.
    """
    try:
        db = new_session()
        try:
            count = RunRepository(db).interrupt_stale()
            if count:
                logger.warning("marked %d stale run(s) interrupted", count)
        finally:
            db.close()
    except Exception:
        logger.warning("stale-run sweep skipped: database unavailable")


app = FastAPI(title="Occasion Agent", lifespan=lifespan)

# The web app calls this service straight from the browser during local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(runs.router, prefix="/runs", tags=["runs"])
app.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
app.include_router(voice.router, prefix="/voice", tags=["voice"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(computer_use.router, prefix="/api/computer-use", tags=["computer-use"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
