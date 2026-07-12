"""Background execution of long agent runs.

The HTTP layer must not hold a request open for the minutes a browser session (or
a whole workflow) takes, so chat turns and approved actions run here instead: a
`running` row goes into agent_runs immediately, the work executes as an asyncio
task on the service's event loop, and the row settles to completed/failed when it
ends. Clients poll the row — the same posture the supervisor takes toward H.

Sessions: each run's memory gets its own database Session for the run's lifetime
(the request's session dies with the response), and every bookkeeping step opens a
short-lived one. Memory stays on the event-loop thread throughout, honoring
core/state.py's thread rule. A process crash strands rows at `running`; the boot
sweep in main.py marks them interrupted so pollers see an honest terminal state.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from uuid import uuid4

from sqlalchemy.orm import Session

from core.orchestrator import Orchestrator
from core.state import Memory
from database.connection import new_session
from database.repositories.event_repository import EventRepository
from database.repositories.memory_repository import MemoryRepository
from database.repositories.run_repository import COMPLETED, FAILED, RunRecord, RunRepository
from integrations.h_company.schemas import SessionResult
from models.task import Task

logger = logging.getLogger(__name__)

CHAT = "chat"
BOOKING = "booking"


class RunManager:
    """Starts runs and settles their rows; the process-wide instance lives below.

    The factory seams exist for tests: `session_factory` swaps the database,
    `orchestrator_factory` swaps the real fleet for a fake. `bind` captures the
    event loop at startup so sync (threadpool) route handlers can start runs too.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = new_session,
        orchestrator_factory: Callable[[Session], Orchestrator] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._orchestrator_factory = orchestrator_factory or (
            lambda db: Orchestrator(memory=Memory(MemoryRepository(db)))
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: set[asyncio.Task] = set()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start_chat(self, message: str, event_id: str | None) -> RunRecord:
        record = self._create(kind=CHAT, title=message, event_id=event_id)
        self._spawn(self._run_chat(record.id, message, event_id))
        return record

    def start_booking(self, action: dict, *, approval_note: str) -> RunRecord:
        vendor = action.get("candidate", {}).get("name", "vendor")
        record = self._create(kind=BOOKING, title=f"Book {vendor}", event_id=action.get("event_id"))
        self._spawn(self._run_booking(record.id, action, approval_note))
        return record

    async def _run_chat(self, run_id: str, message: str, event_id: str | None) -> None:
        memory_db = self._session_factory()
        try:
            orchestrator = self._orchestrator_factory(memory_db)
            task: str | Task = message
            if event_id is not None:
                task = Task(id=f"task-{uuid4().hex[:8]}", event_id=event_id, title=message)
            run = await orchestrator.run_task(task)
            self._finish(run_id, event_id, agent=run.agent, reason=run.reason, result=run.result)
        except Exception as exc:  # the row must settle even when the run machinery raises
            logger.exception("chat run %s crashed", run_id)
            self._finish(run_id, event_id, agent=None, reason=None, result=_crash(exc))
        finally:
            memory_db.close()

    async def _run_booking(self, run_id: str, action: dict, approval_note: str) -> None:
        # Imported here, not at module top: the workflow stack pulls in the whole fleet.
        from workflows.vendor_sourcing import VendorCandidate, VendorSourcingWorkflow

        event_id = action.get("event_id")
        memory_db = self._session_factory()
        try:
            workflow = VendorSourcingWorkflow(memory=Memory(MemoryRepository(memory_db)))
            candidate = VendorCandidate.model_validate(action["candidate"])
            run = await workflow.book(
                candidate,
                event_id=event_id,
                approval=approval_note,
                budget_cap_usd=action.get("budget_cap_usd"),
            )
            self._finish(run_id, event_id, agent=run.agent, reason=run.reason, result=run.result)
        except Exception as exc:
            logger.exception("booking run %s crashed", run_id)
            self._finish(run_id, event_id, agent=None, reason=None, result=_crash(exc))
        finally:
            memory_db.close()

    def _create(self, *, kind: str, title: str, event_id: str | None) -> RunRecord:
        db = self._session_factory()
        try:
            record = RunRepository(db).create(
                run_id=f"run-{uuid4().hex[:10]}", kind=kind, title=title, event_id=event_id
            )
            if event_id is not None:
                verb = "Executing approved booking" if kind == BOOKING else "Started working on"
                EventRepository(db).add_activity(
                    event_id,
                    agent="Occasion",
                    tone="blue",
                    description=f"{verb} “{_clip(title)}”.",
                )
            return record
        finally:
            db.close()

    def _finish(
        self, run_id: str, event_id: str | None, *, agent: str | None, reason: str | None, result: SessionResult
    ) -> None:
        db = self._session_factory()
        try:
            RunRepository(db).finish(
                run_id,
                status=COMPLETED if result.succeeded else FAILED,
                agent=agent,
                reason=reason,
                result=result.model_dump(mode="json"),
            )
            if event_id is not None:
                name = _display_agent(agent)
                line = (
                    f"{name} finished: {_clip(result.answer or 'done')}"
                    if result.succeeded
                    else f"{name} couldn't finish: {_clip(result.error or result.status)}"
                )
                EventRepository(db).add_activity(
                    event_id, agent=name, tone="green" if result.succeeded else "amber", description=line
                )
        except Exception:  # bookkeeping must never take the run task down with it
            logger.exception("failed to settle run %s", run_id)
        finally:
            db.close()

    def _spawn(self, coro: Coroutine) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Called from a threadpool (sync route handler); hand off to the bound loop.
            if self._loop is None:
                coro.close()
                raise RuntimeError("RunManager.bind was not called at startup")
            asyncio.run_coroutine_threadsafe(coro, self._loop)
            return
        task = loop.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)


def _crash(exc: Exception) -> SessionResult:
    return SessionResult(succeeded=False, status="error", error=str(exc))


def _display_agent(agent: str | None) -> str:
    if not agent:
        return "Occasion"
    # "h/web-surfer-flash" -> "Web surfer flash", "workflow/vendor_sourcing" -> "Vendor sourcing"
    return agent.split("/")[-1].replace("-", " ").replace("_", " ").capitalize()


def _clip(text: str, max_length: int = 110) -> str:
    text = " ".join(text.split())  # collapse newlines from multi-line task briefs
    return text if len(text) <= max_length else f"{text[:max_length]}…"


run_manager = RunManager()
