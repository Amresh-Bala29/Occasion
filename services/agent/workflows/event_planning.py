"""End-to-end event planning workflow.

Turns a client brief into a complete event plan and the research tasks to execute it:

1. The requirements agent structures the brief (browserless Holo completion).
2. A deep Holo completion synthesizes the full plan — timeline, budget, checklist,
   vendor categories, deadlines, schedules, backups, and risks.
3. Pure code derives one pinned, guard-railed research task per vendor category.
4. Optionally, the scheduling agent puts the plan's key deadlines on the calendar.

This module is the pipeline's import root: the sourcing and outreach workflows build
on its plan models and shared helpers.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import TYPE_CHECKING, Literal, TypeVar

import httpx
from pydantic import BaseModel, Field

from agents.requirements_agent import EventRequirements, merge_requirements, remember_requirements
from core.orchestrator import Orchestrator, TaskRun
from integrations.h_company.client import HClient, run_structured_completion
from integrations.h_company.schemas import MODEL_DEEP, SessionResult
from memory.event_memory import PLAN_SNAPSHOT, REQUIREMENTS
from memory.vector_store import event_scope
from models.task import Task

if TYPE_CHECKING:
    from core.state import Memory

ModelT = TypeVar("ModelT", bound=BaseModel)

# Each category name doubles as its agent's roster name, so every planned category is
# dispatchable by construction (test-asserted against DOMAIN_AGENTS).
SOURCEABLE_CATEGORIES: tuple[str, ...] = (
    "venue",
    "catering",
    "staffing",
    "entertainment",
    "decorations",
    "merchandise",
)

VendorCategory = Literal["venue", "catering", "staffing", "entertainment", "decorations", "merchandise"]


class PlanMilestone(BaseModel):
    """One dated step on the road to the event."""

    date: str = Field(description="ISO date, or a T-minus offset like 'T-6 weeks' when the event date is unknown.")
    title: str
    details: str | None = None


class BudgetAllocation(BaseModel):
    """How much of the budget one spending category gets, and why."""

    category: str
    estimated_usd: float
    rationale: str | None = None


class ChecklistItem(BaseModel):
    title: str
    category: str = "general"
    due: str | None = None


class VendorCategoryPlan(BaseModel):
    """What one vendor category must deliver — the seed for its research task."""

    category: VendorCategory
    requirements_summary: str = Field(
        description="Self-sufficient brief for a researcher who never saw the client conversation."
    )
    budget_usd: float | None = None
    priority: str | None = None


class KeyDeadline(BaseModel):
    date: str
    title: str
    consequence: str | None = None


class ScheduleEntry(BaseModel):
    when: str
    what: str
    who: str | None = None


class RiskItem(BaseModel):
    risk: str
    likelihood: str
    impact: str
    mitigation: str


class BackupOption(BaseModel):
    scenario: str
    fallback: str


class EventPlan(BaseModel):
    """The full event plan: the answer schema for the synthesis completion."""

    event_summary: str
    event_date: str | None = Field(
        None, description="The event's resolved calendar date as YYYY-MM-DD; null when genuinely unknown."
    )
    timeline: list[PlanMilestone] = []
    budget: list[BudgetAllocation] = []
    total_budget_usd: float | None = None
    checklist: list[ChecklistItem] = []
    vendor_categories: list[VendorCategoryPlan] = []
    key_deadlines: list[KeyDeadline] = []
    delivery_schedule: list[ScheduleEntry] = []
    staffing_schedule: list[ScheduleEntry] = []
    backups: list[BackupOption] = []
    risks: list[RiskItem] = []


class PlanningReport(BaseModel):
    """Everything one planning run produced, stage by stage.

    Raw runs are kept alongside the parsed views so callers always have the audit
    trail (session ids, agent-view URLs) even for stages that failed.
    """

    event_id: str
    brief: str
    requirements_run: TaskRun
    requirements: EventRequirements | None = None
    plan_run: SessionResult | None = None
    plan: EventPlan | None = None
    sourcing_tasks: list[Task] = []
    calendar_run: TaskRun | None = None
    succeeded: bool = False


PLAN_INSTRUCTIONS = """\
You are Occasion's event planning strategist. From a client brief and its extracted
requirements, produce the complete plan for delivering the event.

Deliverables:
- event_summary: the event in two sentences, including date, location, and headcount.
- event_date: the event's calendar date as YYYY-MM-DD when it can be resolved (infer the
  year the same way the timeline does); null when genuinely unknown.
- timeline: dated milestones from today through post-event wrap-up.
- budget: an allocation per spending category, with total_budget_usd as their sum.
- checklist: every task someone must do, categorized and dated where possible.
- vendor_categories: only the categories this event actually needs. Each
  requirements_summary must stand alone for a researcher who never saw the brief:
  restate the date, location, headcount, and every constraint that category must honor.
- key_deadlines: the dates that cannot slip, each with its consequence.
- delivery_schedule and staffing_schedule: when things and people must arrive.
- backups: a fallback for each way the plan most plausibly breaks.
- risks: honest likelihood, impact, and mitigation for each.

Rules:
- Plan only from stated facts. Put unknowns into risks or the checklist as questions
  to resolve — never invent answers.
- Keep allocations within the stated budget; if none was stated, say what you assumed.
- Use concrete dates when the event date is known, otherwise T-minus offsets like
  'T-6 weeks'."""


class EventPlanningWorkflow:
    """Sequential planning pipeline: brief -> requirements -> plan -> sourcing tasks.

    A failed stage returns a partial report rather than raising, so callers always
    see what did run. The constructor seams mirror the Orchestrator's: `client`
    backs browser sessions, `http_client` backs Models API completions.
    """

    def __init__(
        self,
        client: HClient | None = None,
        http_client: httpx.Client | None = None,
        *,
        memory: Memory | None = None,
    ) -> None:
        self._orchestrator = Orchestrator(client=client, http_client=http_client, memory=memory)
        self._memory = memory
        self._http = http_client

    async def run(
        self, brief: str, *, event_id: str, schedule_deadlines: bool = False, user_id: str | None = None
    ) -> PlanningReport:
        """Plan the event described by `brief`; browserless unless `schedule_deadlines`."""
        requirements_run = await self._parse_requirements(brief, event_id)
        report = PlanningReport(event_id=event_id, brief=brief, requirements_run=requirements_run)
        report.requirements = structured(requirements_run.result, EventRequirements)
        if report.requirements is None:
            return report  # nothing downstream is meaningful without requirements
        report.requirements = self._remember_requirements(report.requirements, event_id=event_id, user_id=user_id)

        # A snapshot from a prior run lets a re-run skip the expensive synthesis completion.
        report.plan = self._recalled_plan(event_id)
        if report.plan is None:
            report.plan_run = await self._synthesize_plan(
                brief, report.requirements, event_id=event_id, user_id=user_id
            )
            report.plan = structured(report.plan_run, EventPlan)
            if report.plan is None:
                return report
            if self._memory is not None:
                self._memory.event(event_id).set(PLAN_SNAPSHOT, report.plan.model_dump(mode="json"))

        report.sourcing_tasks = sourcing_tasks(report.plan, event_id)
        if schedule_deadlines and report.plan.key_deadlines:
            report.calendar_run = await self._schedule_deadlines(report.plan, event_id)
        # Calendar entries are reversible and the plan already exists, so a calendar
        # failure stays on its own run without failing the planning itself.
        report.succeeded = True
        return report

    async def _parse_requirements(self, brief: str, event_id: str) -> TaskRun:
        task = Task(
            id=f"{event_id}-requirements",
            event_id=event_id,
            title=brief,
            assignee_agent="requirements",
        )
        return await self._orchestrator.run_task(task)

    async def _synthesize_plan(
        self, brief: str, requirements: EventRequirements, *, event_id: str | None = None, user_id: str | None = None
    ) -> SessionResult:
        sections = [
            f"Client brief:\n{brief}",
            f"Extracted requirements (JSON):\n{requirements.model_dump_json()}",
            # The model has no clock, and every deadline offset depends on it.
            f"Today's date: {date.today().isoformat()}",
        ]
        sections.extend(memory_sections(self._memory, brief, event_id=event_id, user_id=user_id))
        return await complete("\n\n".join(sections), PLAN_INSTRUCTIONS, EventPlan, http_client=self._http)

    def _remember_requirements(
        self, requirements: EventRequirements, *, event_id: str, user_id: str | None
    ) -> EventRequirements:
        """Merge with the stored brief, snapshot it, and accumulate preferences.

        The kickoff re-extracts requirements from its own brief, which can drop facts the
        intake already settled; merging keeps the snapshot cumulative. Returns what the
        downstream stages should plan against.
        """
        if self._memory is None:
            return requirements
        prior = self._memory.event(event_id).get(REQUIREMENTS)
        if prior is not None:
            requirements = merge_requirements(EventRequirements.model_validate(prior), requirements)
        remember_requirements(self._memory, requirements, event_id=event_id, user_id=user_id)
        return requirements

    def _recalled_plan(self, event_id: str) -> EventPlan | None:
        if self._memory is None:
            return None
        snapshot = self._memory.event(event_id).get(PLAN_SNAPSHOT)
        return EventPlan.model_validate(snapshot) if snapshot is not None else None

    async def _schedule_deadlines(self, plan: EventPlan, event_id: str) -> TaskRun:
        lines = ["Create one calendar entry per key deadline below; skip any that already exist."]
        for number, deadline in enumerate(plan.key_deadlines, 1):
            entry = f"{number}. {deadline.date} — {deadline.title}"
            if deadline.consequence:
                entry += f" (at stake: {deadline.consequence})"
            lines.append(entry)
        task = Task(
            id=f"{event_id}-deadlines",
            event_id=event_id,
            title="\n".join(lines),
            assignee_agent="scheduling",
        )
        return await self._orchestrator.run_task(task)


def sourcing_tasks(plan: EventPlan, event_id: str) -> list[Task]:
    """One pinned research task per vendor category in the plan.

    These seed titles are runnable as-is, and VendorSourcingWorkflow uses them as
    the fallback when its brief compiler fails — one source of truth, no drift.
    """
    return [
        Task(
            id=f"{event_id}-source-{category.category}",
            event_id=event_id,
            title=_seed_brief(plan, category),
            assignee_agent=category.category,
        )
        for category in plan.vendor_categories
    ]


def _seed_brief(plan: EventPlan, category: VendorCategoryPlan) -> str:
    lines = [
        f"Research and compare {category.category} options for this event.",
        f"Event: {plan.event_summary}",
        f"What this category needs: {category.requirements_summary}",
        "Find several strong candidates and report capacity, pricing, availability, and "
        "how to contact each one, verified on the page.",
    ]
    return "\n".join(lines + research_guards(category.budget_usd))


def research_guards(budget_usd: float | None) -> list[str]:
    """Literal guard lines appended to every research task.

    GUARDRAILS keys budget and commitment behavior off exact task text, so these
    lines are always code-authored — never left to a model to phrase.
    """
    lines = []
    if budget_usd is not None:
        lines.append(f"Budget cap for this category: ${budget_usd:.0f}; stop and report rather than exceed it.")
    lines.append("Research and compare only — do not contact vendors, book, or pay anything.")
    return lines


def structured(result: SessionResult, schema: type[ModelT]) -> ModelT | None:
    """The result's validated payload as `schema`, or None for a failed or empty run.

    The payload was already validated against the same schema upstream (by the SDK
    or the Models API call), so this is a parse back into the typed model.
    """
    if not result.succeeded or result.data is None:
        return None
    return schema.model_validate(result.data)


async def complete(
    prompt: str,
    instructions: str,
    schema: type[ModelT],
    *,
    model: str = MODEL_DEEP,
    http_client: httpx.Client | None = None,
) -> SessionResult:
    """One browserless Holo completion, off the event loop like every blocking H call."""
    return await asyncio.to_thread(
        run_structured_completion,
        prompt,
        instructions,
        schema,
        model=model,
        http_client=http_client,
    )


def memory_sections(
    memory: Memory | None, query: str, *, event_id: str | None = None, user_id: str | None = None
) -> list[str]:
    """Preference and recalled-research prompt sections drawn from memory.

    Empty when there is no memory or nothing relevant, so callers append unconditionally.
    Shared by the planning and sourcing prompts so both fold the same context the same way.
    """
    if memory is None:
        return []
    sections = []
    note = memory.preferences.get(user_id).as_prompt_note()
    if note:
        sections.append(note)
    if event_id is not None:
        hits = memory.semantic.search(query, scope=event_scope(event_id), limit=3)
        if hits:
            sections.append("Notes recalled from earlier research:\n" + "\n\n".join(h.document.content for h in hits))
    return sections


def slug(text: str) -> str:
    """A lowercase, dash-separated fragment for readable task ids."""
    parts = "".join(ch if ch.isalnum() else " " for ch in text.lower()).split()
    return "-".join(parts) or "item"
