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
from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from agents.requirements_agent import (
    EventRequirements,
    RequirementsAgent,
    merge_requirements,
    remember_requirements,
)
from core.config import settings
from core.orchestrator import Orchestrator, TaskRun
from core.state import Memory
from database.connection import new_session
from database.repositories.event_repository import EventRepository
from database.repositories.memory_repository import MemoryRepository
from database.repositories.run_repository import COMPLETED, FAILED, RUNNING, RunRecord, RunRepository
from integrations.h_company.client import HClient
from integrations.h_company.schemas import SessionResult
from memory.event_memory import DEMO_FIXTURE, PLAN_SNAPSHOT, REQUIREMENTS
from memory.vector_store import CHAT_NOTE, DECISION, event_scope
from models.task import Task

if TYPE_CHECKING:
    from workflows.event_planning import EventPlan

logger = logging.getLogger(__name__)

CHAT = "chat"
BOOKING = "booking"

# Demo shortcut: an intake prompt naming one of these hands the whole dashboard a curated
# fixture event (keyed by id), overriding whatever the live pipeline produces. Insertion
# order is match precedence.
_DEMO_KEYWORDS = {"cake": "rooftop-party", "pizza": "hackathon"}


def _match_demo_fixture(message: str) -> str | None:
    """The fixture event id for the first demo keyword in `message`, else None."""
    lowered = message.lower()
    for keyword, fixture_id in _DEMO_KEYWORDS.items():
        if keyword in lowered:
            return fixture_id
    return None


class RunManager:
    """Starts runs and settles their rows; the process-wide instance lives below.

    The factory seams exist for tests: `session_factory` swaps the database,
    `orchestrator_factory` swaps the real fleet for a fake, and `h_client_factory` /
    `http_client` back the boot-time recovery (H session lookups and synthesis
    completions). `bind` captures the event loop at startup so sync (threadpool)
    route handlers can start runs too.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = new_session,
        orchestrator_factory: Callable[[Session], Orchestrator] | None = None,
        h_client_factory: Callable[[], HClient] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._orchestrator_factory = orchestrator_factory or (
            lambda db: Orchestrator(memory=Memory(MemoryRepository(db)))
        )
        self._h_client_factory = h_client_factory
        self._http = http_client
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: set[asyncio.Task] = set()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start_chat(self, message: str, event_id: str | None, *, agent: str | None = None) -> RunRecord:
        # Intake turns pin "requirements"; a demo keyword there swaps the dashboard to a fixture.
        if agent == "requirements" and event_id is not None:
            self._flag_demo_fixture(event_id, message)
        record = self._create(kind=CHAT, title=message, event_id=event_id)
        self._spawn(self._run_chat(record.id, message, event_id, agent))
        return record

    def start_booking(self, action: dict, *, approval_note: str) -> RunRecord:
        vendor = action.get("candidate", {}).get("name", "vendor")
        record = self._create(kind=BOOKING, title=f"Book {vendor}", event_id=action.get("event_id"))
        self._spawn(self._run_booking(record.id, action, approval_note))
        return record

    def start_recovery(self) -> None:
        """Reconcile runs a previous process stranded; spawned at boot, never awaited."""
        self._spawn(self._reconcile_interrupted())

    async def _run_chat(self, run_id: str, message: str, event_id: str | None, agent: str | None = None) -> None:
        # Opened inside the try: a failed session open must still settle the row.
        memory_db: Session | None = None
        published: set[str] = set()
        try:
            memory_db = self._session_factory()
            orchestrator = self._orchestrator_factory(memory_db)
            task: str | Task = message
            if event_id is not None:
                # Stages publish to the dashboard as they finish, so a 40-minute
                # sourcing fan-out no longer keeps the plan panels empty.
                orchestrator.on_stage = self._stage_publisher(event_id, published)
                # A preset assignee skips routing; the orchestrator fails honestly on unknown names.
                task = Task(id=f"task-{uuid4().hex[:8]}", event_id=event_id, title=message, assignee_agent=agent)
            run = await orchestrator.run_task(task)
            run = self._merge_and_remember_requirements(memory_db, run, event_id)
            self._publish_workflow_outputs(run, event_id, skip_stages=published)
            self._remember_chat_note(memory_db, run, message, event_id)
            self._finish(run_id, event_id, agent=run.agent, reason=run.reason, result=run.result)
        except Exception as exc:  # the row must settle even when the run machinery raises
            logger.exception("chat run %s crashed", run_id)
            self._finish(run_id, event_id, agent=None, reason=None, result=_crash(exc))
        finally:
            if memory_db is not None:
                memory_db.close()

    async def _run_booking(self, run_id: str, action: dict, approval_note: str) -> None:
        # Imported here, not at module top: the workflow stack pulls in the whole fleet.
        from workflows.vendor_sourcing import VendorCandidate, VendorSourcingWorkflow

        event_id = action.get("event_id")
        # Opened inside the try: a failed session open must still settle the row.
        memory_db: Session | None = None
        try:
            memory_db = self._session_factory()
            workflow = VendorSourcingWorkflow(memory=Memory(MemoryRepository(memory_db)))
            candidate = VendorCandidate.model_validate(action["candidate"])
            run = await workflow.book(
                candidate,
                event_id=event_id,
                approval=approval_note,
                budget_cap_usd=action.get("budget_cap_usd"),
            )
            self._publish_booking_outcome(run, action)
            self._remember_booking_decision(memory_db, run, action)
            self._finish(run_id, event_id, agent=run.agent, reason=run.reason, result=run.result)
        except Exception as exc:
            logger.exception("booking run %s crashed", run_id)
            self._finish(run_id, event_id, agent=None, reason=None, result=_crash(exc))
        finally:
            if memory_db is not None:
                memory_db.close()

    async def _reconcile_interrupted(self) -> None:
        """Settle every interrupted chat run, recovering what its work left behind.

        The dashboard writer sits at the tail of the run coroutine, so a restart loses
        the write even though the plan snapshot survives in event memory and finished
        research sessions survive on H's servers. This republishes both, then settles
        each stranded row terminal — pollers see an honest state and no later boot
        revisits it. Interrupted bookings are left alone: fabricating a booking
        outcome would be unsafe.
        """
        try:
            db = self._session_factory()
            try:
                stranded = RunRepository(db).list_interrupted(kind=CHAT)
            finally:
                db.close()
        except Exception:
            logger.warning("recovery sweep skipped: database unavailable")
            return
        by_event: dict[str | None, list[RunRecord]] = {}
        for record in stranded:
            by_event.setdefault(record.event_id, []).append(record)
        for event_id, records in by_event.items():
            try:  # one broken event must not strand the rest
                if event_id is None:
                    self._settle_stranded(records, recovered=[])
                else:
                    await self._recover_event(event_id, records)
            except Exception:
                logger.exception("recovery failed for event %s", event_id)

    async def _recover_event(self, event_id: str, records: list[RunRecord]) -> None:
        """Republish one event's stranded outputs, then settle its interrupted rows."""
        recovered: list[str] = []
        db = self._session_factory()
        try:
            runs_repo = RunRepository(db)
            repo = EventRepository(db)
            if any(record.status == RUNNING for record in runs_repo.list_for_event(event_id)):
                # A newer run owns this event now; recovering under it would double-write.
                failure = SessionResult(
                    succeeded=False,
                    status="interrupted",
                    error="interrupted by a service restart; a newer run took over",
                )
                for record in records:
                    runs_repo.finish(
                        record.id,
                        status=FAILED,
                        agent=record.agent,
                        reason="superseded by a newer run",
                        result=failure.model_dump(mode="json"),
                    )
                repo.add_activity(
                    event_id,
                    agent="Occasion",
                    tone="amber",
                    description="A restart interrupted an earlier run; the run now in progress has taken over.",
                )
                return
            memory = Memory(MemoryRepository(db))
            plan = self._recovered_plan(memory, event_id)
            if plan is not None and not repo.get_plan(event_id).phases:
                # save_plan always writes the fixed phases, so empty phases ⇔ never published.
                if self._republish_plan(repo, memory, event_id, plan):
                    recovered.append("the event plan")
            if plan is not None and settings.hai_api_key and not repo.get_vendors(event_id):
                count = await self._recover_vendors(repo, memory, event_id, plan)
                if count:
                    recovered.append(f"{count} researched vendors")
            if not recovered:
                repo.add_activity(
                    event_id,
                    agent="Occasion",
                    tone="amber",
                    description=(
                        "A previous run was interrupted by a restart and nothing could be "
                        "recovered — you may want to start it again."
                    ),
                )
        finally:
            db.close()
        self._settle_stranded(records, recovered=recovered)

    def _recovered_plan(self, memory: Memory, event_id: str) -> EventPlan | None:
        """The plan snapshot a dead run left in event memory, if it still parses."""
        # Imported here, not at module top: the workflow stack pulls in the whole fleet.
        from workflows.event_planning import EventPlan

        snapshot = memory.event(event_id).get(PLAN_SNAPSHOT)
        if snapshot is None:
            return None
        try:
            return EventPlan.model_validate(snapshot)
        except Exception:
            logger.exception("event %s: stored plan snapshot no longer parses", event_id)
            return None

    def _republish_plan(self, repo: EventRepository, memory: Memory, event_id: str, plan: EventPlan) -> bool:
        """Publish the recovered plan; guarded so a plan failure can't block vendor recovery."""
        try:
            requirements_json = memory.event(event_id).get(REQUIREMENTS)
            requirements = EventRequirements.model_validate(requirements_json) if requirements_json else None
            repo.save_plan(event_id, plan, requirements=requirements)
            repo.add_activity(
                event_id,
                agent="Occasion",
                tone="green",
                description="Recovered the event plan from an interrupted run — it's live on the dashboard.",
            )
            return True
        except Exception:
            logger.exception("failed to republish the recovered plan for event %s", event_id)
            repo.db.rollback()  # the failed write leaves the session unusable until rolled back
            return False

    async def _recover_vendors(self, repo: EventRepository, memory: Memory, event_id: str, plan: EventPlan) -> int:
        """Rebuild the vendor shortlist from the research sessions H still holds.

        Returns how many candidates reached the vendors board. The H lookups block, so
        they hop to a worker thread like every SDK call; synthesis then runs through
        the same seam the live workflow uses, so the shortlist (and its memory
        snapshot) come out identical to an uninterrupted run's.
        """
        # Imported here, not at module top: the workflow stack pulls in the whole fleet.
        from workflows.event_planning import sourcing_tasks
        from workflows.vendor_sourcing import VendorSourcingWorkflow

        client = self._h_client_factory() if self._h_client_factory is not None else HClient.from_settings()
        categories = [category.category for category in plan.vendor_categories]
        results = await asyncio.to_thread(client.completed_research, event_id, categories)
        if not results:
            return 0
        # Tasks and runs align by index; categories with no surviving session become
        # gaps through the seam's enforcement rather than fabricated failures here.
        tasks = [task for task in sourcing_tasks(plan, event_id) if task.assignee_agent in results]
        runs = [
            TaskRun(task_id=task.id, agent=task.assignee_agent, result=results[task.assignee_agent])
            for task in tasks
        ]
        workflow = VendorSourcingWorkflow(http_client=self._http, memory=memory)
        _, shortlist = await workflow.shortlist_findings(plan, tasks, runs, event_id=event_id)
        if shortlist is None or not shortlist.candidates:
            return 0
        repo.save_vendors(event_id, shortlist)
        repo.add_activity(
            event_id,
            agent="Occasion",
            tone="green",
            description=(
                f"Recovered vendor research from an interrupted run — "
                f"{len(shortlist.candidates)} candidates are on the vendors board."
            ),
        )
        return len(shortlist.candidates)

    def _settle_stranded(self, records: list[RunRecord], *, recovered: list[str]) -> None:
        """Move stranded rows to a terminal state so no later sweep revisits them."""
        if recovered:
            status = COMPLETED
            reason = "recovered after restart"
            result = SessionResult(
                succeeded=True,
                status="completed",
                answer=f"Recovered after a service restart: {', '.join(recovered)}.",
            )
        else:
            status = FAILED
            reason = "interrupted by a service restart"
            result = SessionResult(
                succeeded=False,
                status="interrupted",
                error="interrupted by a service restart; nothing recoverable was found",
            )
        db = self._session_factory()
        try:
            repo = RunRepository(db)
            for record in records:
                repo.finish(
                    record.id, status=status, agent=record.agent, reason=reason, result=result.model_dump(mode="json")
                )
        finally:
            db.close()

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

    def _flag_demo_fixture(self, event_id: str, message: str) -> None:
        """If an intake message names a demo keyword, point this event's dashboard reads at
        the matching fixture. Best-effort: a failure here must never break the chat turn."""
        fixture_id = _match_demo_fixture(message)
        if fixture_id is None:
            return
        db = self._session_factory()
        try:
            MemoryRepository(db).set_event_memory(event_id=event_id, key=DEMO_FIXTURE, value=fixture_id)
        except Exception:
            logger.exception("failed to flag demo fixture for event %s", event_id)
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

    def _stage_publisher(self, event_id: str, published: set[str]) -> Callable[[str, dict], None]:
        """The workflow's on_stage hook: publish each stage as it lands, tracking what stuck."""

        def publish(stage: str, payload: dict) -> None:
            if self._publish_stage(event_id, stage, payload):
                published.add(stage)

        return publish

    def _publish_stage(self, event_id: str, stage: str, payload: dict) -> bool:
        """Write one finished workflow stage through to the dashboard tables, mid-run.

        Returns True only when the stage's rows were committed; a failed or empty
        publish returns False so the tail sweep in _publish_workflow_outputs retries
        it. Same posture as that sweep: a publish failure is reported as an amber feed
        line, never raised into the workflow.
        """
        # Imported here, not at module top: the workflow stack pulls in the whole fleet.
        from workflows.event_planning import EventPlan
        from workflows.vendor_sourcing import VendorShortlist

        db = self._session_factory()
        try:
            repo = EventRepository(db)
            if stage == "planning":
                plan_json = payload.get("plan")
                if plan_json is None:
                    return False
                requirements_json = payload.get("requirements")
                requirements = EventRequirements.model_validate(requirements_json) if requirements_json else None
                repo.save_plan(event_id, EventPlan.model_validate(plan_json), requirements=requirements)
                repo.add_activity(
                    event_id,
                    agent="Occasion",
                    tone="green",
                    description="Plan drafted — timeline, budget, and checklist are live on the dashboard.",
                )
                return True
            if stage == "sourcing":
                shortlist_json = payload.get("shortlist")
                # An empty shortlist must not clobber previously published vendors.
                if shortlist_json is None or not shortlist_json.get("candidates"):
                    return False
                repo.save_vendors(event_id, VendorShortlist.model_validate(shortlist_json))
                repo.add_activity(
                    event_id,
                    agent="Occasion",
                    tone="green",
                    description=(
                        f"Vendor research complete — {len(shortlist_json['candidates'])} "
                        "candidates are on the vendors board."
                    ),
                )
                return True
            return False
        except Exception:
            logger.exception("failed to publish the %s stage for event %s", stage, event_id)
            db.rollback()  # the failed write leaves the session unusable until rolled back
            try:
                EventRepository(db).add_activity(
                    event_id,
                    agent="Occasion",
                    tone="amber",
                    description=f"Finished the {stage} stage but couldn't publish it to the dashboard — see server logs.",
                )
            except Exception:
                logger.exception("failed to report the %s publish failure for event %s", stage, event_id)
            return False
        finally:
            db.close()

    def _publish_workflow_outputs(
        self, run: TaskRun, event_id: str | None, *, skip_stages: set[str] | frozenset[str] = frozenset()
    ) -> None:
        """Write a settled workflow's plan and shortlist through to the dashboard tables.

        Workflows snapshot their outputs to agent memory only; the events aggregate the
        dashboard reads is repository-owned, and this is its production writer. Stage
        dumps are read even off a failed chain, so a plan whose sourcing stage died
        still reaches the dashboard. A publish failure must not be silent — it lands
        as an amber feed line — but it never fails a run whose agent work finished.

        `skip_stages` names stages the mid-run hook already published. Rewriting them
        here could regress rows that changed since — the delete-and-rewrite in
        save_vendors would demote a vendor a booking confirmed mid-run.
        """
        if event_id is None or not run.agent or not run.agent.startswith("workflow/"):
            return
        stages = run.result.data or {}
        planning = {} if "planning" in skip_stages else (stages.get("planning") or {})
        sourcing = {} if "sourcing" in skip_stages else (stages.get("sourcing") or {})
        outreach_json = stages.get("outreach") or {}
        plan_json = planning.get("plan")
        shortlist_json = sourcing.get("shortlist")
        if shortlist_json is not None and not shortlist_json.get("candidates"):
            shortlist_json = None  # an empty shortlist must not clobber previously published vendors
        if plan_json is None and shortlist_json is None and not outreach_json:
            return
        # Imported here, not at module top: the workflow stack pulls in the whole fleet.
        from workflows.event_planning import EventPlan
        from workflows.vendor_outreach import OutreachReport
        from workflows.vendor_sourcing import VendorShortlist

        db = self._session_factory()
        try:
            repo = EventRepository(db)
            if plan_json is not None:
                requirements_json = planning.get("requirements")
                requirements = EventRequirements.model_validate(requirements_json) if requirements_json else None
                repo.save_plan(event_id, EventPlan.model_validate(plan_json), requirements=requirements)
            if shortlist_json is not None:
                repo.save_vendors(event_id, VendorShortlist.model_validate(shortlist_json))
            if outreach_json:
                report = OutreachReport.model_validate(outreach_json)
                # candidates and send_runs align by index (OutreachReport's contract).
                contacted = [
                    candidate.name
                    for candidate, send in zip(report.candidates, report.send_runs)
                    if send.result.succeeded
                ]
                if contacted or report.comparison is not None:
                    repo.save_outreach(event_id, contacted=contacted, comparison=report.comparison)
        except Exception:
            logger.exception("failed to publish workflow outputs for event %s", event_id)
            db.rollback()  # the failed write leaves the session unusable until rolled back
            try:
                EventRepository(db).add_activity(
                    event_id,
                    agent="Occasion",
                    tone="amber",
                    description="Finished the work but couldn't publish the results to the dashboard — see server logs.",
                )
            except Exception:
                logger.exception("failed to report the publish failure for event %s", event_id)
        finally:
            db.close()

    def _publish_booking_outcome(self, run: TaskRun, action: dict) -> None:
        """Flip the booked vendor's dashboard row to Confirmed after a successful booking.

        Same posture as _publish_workflow_outputs: the agent's work is already done, so
        a row-update failure is reported (amber line) but never fails the run.
        """
        event_id = action.get("event_id")
        candidate = action.get("candidate") or {}
        name = candidate.get("name")
        if not run.result.succeeded or not event_id or not name:
            return
        db = self._session_factory()
        try:
            EventRepository(db).confirm_vendor(
                event_id,
                name=name,
                category=candidate.get("category"),
                amount_usd=action.get("amount_usd"),
                price_notes=candidate.get("price_notes"),
            )
        except Exception:
            logger.exception("failed to publish booking outcome for event %s", event_id)
            db.rollback()  # the failed write leaves the session unusable until rolled back
            try:
                EventRepository(db).add_activity(
                    event_id,
                    agent="Occasion",
                    tone="amber",
                    description=f"Booked {name} but couldn't update the vendor list — see server logs.",
                )
            except Exception:
                logger.exception("failed to report the booking-publish failure for event %s", event_id)
        finally:
            db.close()

    def _merge_and_remember_requirements(self, memory_db: Session, run: TaskRun, event_id: str | None) -> TaskRun:
        """Merge a requirements turn with the event's stored brief, persist it, return the run.

        Each turn re-extracts the full transcript from scratch, so a later turn can drop a
        fact an earlier one captured; backfilling from the stored snapshot keeps the brief
        cumulative — in memory and in the run row the intake page reads. Only the
        requirements agent yields EventRequirements; every other run passes through
        untouched. This is bookkeeping over the run's own session, so a failure is logged
        and swallowed rather than failing a run that already succeeded.
        """
        if (
            event_id is None
            or run.agent != RequirementsAgent.name
            or not run.result.succeeded
            or run.result.data is None
        ):
            return run
        try:
            memory = Memory(MemoryRepository(memory_db))
            requirements = EventRequirements.model_validate(run.result.data)
            prior = memory.event(event_id).get(REQUIREMENTS)
            if prior is not None:
                requirements = merge_requirements(EventRequirements.model_validate(prior), requirements)
            remember_requirements(memory, requirements, event_id=event_id)
            # Re-dump both representations so `answer` (raw JSON) can't disagree with `data`.
            result = run.result.model_copy(
                update={"data": requirements.model_dump(mode="json"), "answer": requirements.model_dump_json()}
            )
            return run.model_copy(update={"result": result})
        except Exception:  # a memory write must not fail a run that already succeeded
            logger.exception("failed to persist requirements for run on event %s", event_id)
            return run

    def _remember_chat_note(self, memory_db: Session, run: TaskRun, message: str, event_id: str | None) -> None:
        """File a settled chat answer as an event-scoped note so later runs recall it.

        This is what keeps every future H session informed of what was already asked and
        answered in chat: Memory.prompt_context searches these notes back into prompts.
        Requirements turns are skipped (their snapshot lands in event memory) and so are
        workflow runs (their stages file their own research documents). Bookkeeping over
        the run's own session: a failure is logged, never fatal to a finished run.
        """
        if event_id is None or run.agent is None:
            return
        if run.agent == RequirementsAgent.name or run.agent.startswith("workflow/"):
            return
        if not run.result.succeeded or not run.result.answer:
            return
        try:
            Memory(MemoryRepository(memory_db)).semantic.add_document(
                f"Asked: {message}\nAnswer: {run.result.answer}",
                scope=event_scope(event_id, run.agent),
                kind=CHAT_NOTE,
                event_id=event_id,
            )
        except Exception:
            logger.exception("failed to file chat note for event %s", event_id)
            memory_db.rollback()  # the failed write leaves the session unusable until rolled back

    def _remember_booking_decision(self, memory_db: Session, run: TaskRun, action: dict) -> None:
        """File a completed booking as a decision note every later prompt carries.

        Decisions ride into prompts unconditionally (not just on a search match), so the
        content is kept to one clipped line. Same posture as the chat note: logged,
        never fatal.
        """
        event_id = action.get("event_id")
        candidate = action.get("candidate") or {}
        name = candidate.get("name")
        if not run.result.succeeded or not event_id or not name:
            return
        try:
            parts = [f"Booked {name}"]
            if candidate.get("category"):
                parts.append(f"({candidate['category']})")
            if action.get("amount_usd"):
                parts.append(f"for ${action['amount_usd']:.0f}")
            if run.result.answer:
                parts.append(f"— {_clip(run.result.answer, 200)}")
            Memory(MemoryRepository(memory_db)).semantic.add_document(
                " ".join(parts), scope=event_scope(event_id), kind=DECISION, event_id=event_id
            )
        except Exception:
            logger.exception("failed to file booking decision for event %s", event_id)
            memory_db.rollback()  # the failed write leaves the session unusable until rolled back

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
