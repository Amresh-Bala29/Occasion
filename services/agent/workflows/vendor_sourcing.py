"""Vendor discovery and shortlisting workflow.

Turns an event plan into a compared, ranked vendor shortlist:

1. Optionally, H's deep-search agent sweeps the web for candidate vendor URLs.
2. A deep Holo completion compiles each category's needs (plus any discovery finds)
   into a browser brief shaped the way H's docs say runs succeed — explicit start
   URL, ordered steps, success criteria.
3. The category agents research in parallel waves of three (the H session cap);
   a full run can take a while — each research session is bounded at 40 minutes.
4. A deep Holo completion merges every category's findings into one shortlist with
   per-category rankings, gaps, and cross-category tradeoffs.

Booking is deliberately a separate, approval-gated call (`book`), never part of the
research run.
"""

from __future__ import annotations

import json
from datetime import date

import httpx
from pydantic import BaseModel, Field

from agents.requirements_agent import EventRequirements
from core.orchestrator import Orchestrator, TaskRun
from integrations.h_company.client import HClient
from integrations.h_company.schemas import SessionResult
from models.task import Task
from workflows.event_planning import (
    EventPlan,
    VendorCategory,
    complete,
    research_guards,
    slug,
    sourcing_tasks,
    structured,
)

# Retail-style carts check out through purchasing — the only agent whose remit covers
# completing a purchase. Relationship bookings stay with the category specialist,
# whose own instructions cover booking after approval.
_CHECKOUT_CATEGORIES = frozenset({"decorations", "merchandise"})


class ResearchBrief(BaseModel):
    """One compiled browser brief, in the shape H's docs say succeeds."""

    category: VendorCategory
    objective: str
    start_url: str = Field(description="Concrete page to start from: a marketplace, directory, or search URL.")
    steps: list[str] = []
    success_criteria: str
    constraints: list[str] = []


class SourcingBriefs(BaseModel):
    """The brief compiler's structured answer."""

    briefs: list[ResearchBrief] = []


class VendorCandidate(BaseModel):
    """One vendor from the research, normalized for comparison and outreach."""

    category: VendorCategory
    name: str
    url: str
    price_notes: str | None = None
    availability: str | None = None
    contact_path: str | None = Field(None, description="Form URL, email, or phone, copied verbatim from research.")
    fit_rationale: str | None = None
    concerns: list[str] = []
    rank: int = Field(1, description="1 = best fit within its category.")


class CategoryRecommendation(BaseModel):
    category: str
    choice: str
    why: str
    tradeoffs: str | None = None


class VendorShortlist(BaseModel):
    """The synthesis answer: ranked candidates, picks, and honest gaps."""

    candidates: list[VendorCandidate] = []
    recommendations: list[CategoryRecommendation] = []
    gaps: list[str] = Field(default=[], description="Categories whose research failed or found nothing viable.")
    next_steps: list[str] = []


class SourcingReport(BaseModel):
    """Everything one sourcing run produced, stage by stage.

    Research runs and tasks align by index, so the exact prompt behind every
    session stays auditable next to its result.
    """

    event_id: str
    discovery_run: TaskRun | None = None
    briefs_run: SessionResult | None = None
    briefs: list[ResearchBrief] = []
    research_tasks: list[Task] = []
    research_runs: list[TaskRun] = []
    shortlist_run: SessionResult | None = None
    shortlist: VendorShortlist | None = None
    succeeded: bool = False


BRIEF_INSTRUCTIONS = """\
You write browser-run briefs for computer-use agents researching event vendors.
Produce one brief per category listed in the prompt.

Each brief:
- start_url: one concrete page to begin on — a discovery URL from the prompt when
  one fits, otherwise the category's natural marketplace or a specific search URL.
- steps: 3-7 imperative steps naming the controls to use (search boxes, filters,
  date pickers) and what to verify on each page before moving on.
- success_criteria: how many candidates to find and which facts — capacity, price,
  availability — must be verified on the page, never inferred.
- constraints: restate the event's date, location, headcount, budget, and any
  dietary or accessibility needs the category must honor.
- Research only: no brief may include contacting vendors, booking, or paying;
  a later workflow owns outreach."""

SHORTLIST_INSTRUCTIONS = """\
You merge vendor research from several specialist agents into one shortlist.

Rules:
- Rank candidates within each category; copy names, URLs, and contact paths
  verbatim from the research JSON — never invent or normalize them.
- Respect each category's budget cap when ranking, and flag options that exceed it.
- Record a gap for every category whose research failed or found nothing viable.
- Note cross-category tradeoffs (money saved in one category funding another) in
  the recommendations.
- next_steps names the specific candidates to contact for quotes."""


class VendorSourcingWorkflow:
    """Sequential sourcing pipeline: plan -> briefs -> research fan-out -> shortlist.

    A failed enhancement stage falls back to the plan's seed briefs; a failed
    research run becomes a gap the synthesis must acknowledge. Nothing raises on
    agent failure — the report carries every run either way.
    """

    def __init__(self, client: HClient | None = None, http_client: httpx.Client | None = None) -> None:
        self._orchestrator = Orchestrator(client=client, http_client=http_client)
        self._http = http_client

    async def run(
        self,
        plan: EventPlan,
        *,
        event_id: str,
        requirements: EventRequirements | None = None,
        discover: bool = False,
    ) -> SourcingReport:
        """Research every vendor category in the plan and shortlist the findings.

        `discover` adds a deep-search sweep for candidate URLs before research; it
        improves the briefs but holds one of the three session slots for up to
        20 minutes, so it is opt-in.
        """
        report = SourcingReport(event_id=event_id)
        discovery_notes: str | None = None
        if discover:
            report.discovery_run = await self._discover(plan, event_id)
            if report.discovery_run.result.succeeded:
                discovery_notes = report.discovery_run.result.answer

        report.briefs_run = await self._compile_briefs(plan, requirements, discovery_notes)
        compiled = structured(report.briefs_run, SourcingBriefs)
        report.briefs = compiled.briefs if compiled else []

        report.research_tasks = self._research_tasks(plan, report.briefs, event_id)
        report.research_runs = await self._orchestrator.run_tasks(report.research_tasks)

        report.shortlist_run = await self._synthesize(plan, report.research_tasks, report.research_runs)
        report.shortlist = structured(report.shortlist_run, VendorShortlist)
        report.succeeded = report.shortlist is not None
        return report

    async def book(
        self,
        candidate: VendorCandidate,
        *,
        event_id: str,
        approval: str,
        budget_cap_usd: float | None = None,
    ) -> TaskRun:
        """Book one shortlisted vendor. `approval` must quote the user's explicit go-ahead.

        The approval text is embedded verbatim in the task, which is the exact-text
        convention the agents' GUARDRAILS key binding commitments on.
        """
        if not approval.strip():
            raise ValueError("approval text is required to book; bookings are binding commitments")
        assignee = "purchasing" if candidate.category in _CHECKOUT_CATEGORIES else candidate.category
        lines = [f"Complete the booking with {candidate.name}: {candidate.url}"]
        if candidate.availability:
            lines.append(f"Requested slot: {candidate.availability}")
        if candidate.price_notes:
            lines.append(f"Expected pricing: {candidate.price_notes}")
        lines.append(f"The user has explicitly approved this booking: {approval}")
        if budget_cap_usd is not None:
            lines.append(f"Budget cap: ${budget_cap_usd:.0f}; stop and report rather than exceed it.")
        lines.append(
            "If the site demands more than the approved amount, or a contract beyond this "
            "booking, stop and report instead of proceeding."
        )
        task = Task(
            id=f"{event_id}-book-{slug(candidate.name)}",
            event_id=event_id,
            title="\n".join(lines),
            assignee_agent=assignee,
        )
        return await self._orchestrator.run_task(task)

    async def _discover(self, plan: EventPlan, event_id: str) -> TaskRun:
        categories = ", ".join(category.category for category in plan.vendor_categories)
        title = "\n".join(
            [
                f"Find candidate vendors for this event: {plan.event_summary}",
                f"Vendor categories needed: {categories}.",
                "For each category, list 3 to 5 specific vendor or marketplace-listing URLs "
                "worth researching, with a one-line note on fit. Cite the exact URL for "
                "every claim.",
            ]
        )
        task = Task(id=f"{event_id}-discover", event_id=event_id, title=title, assignee_agent="h/deep-search-pro")
        return await self._orchestrator.run_task(task)

    async def _compile_briefs(
        self,
        plan: EventPlan,
        requirements: EventRequirements | None,
        discovery_notes: str | None,
    ) -> SessionResult:
        sections = [f"Event: {plan.event_summary}", f"Today's date: {date.today().isoformat()}"]
        if requirements is not None:
            sections.append(f"Requirements (JSON):\n{requirements.model_dump_json()}")
        for category in plan.vendor_categories:
            block = f"Category {category.category}: {category.requirements_summary}"
            if category.budget_usd is not None:
                block += f"\nBudget: ${category.budget_usd:.0f}"
            sections.append(block)
        if discovery_notes:
            sections.append(f"Discovery notes (URLs from a prior research sweep):\n{discovery_notes}")
        return await complete("\n\n".join(sections), BRIEF_INSTRUCTIONS, SourcingBriefs, http_client=self._http)

    def _research_tasks(self, plan: EventPlan, briefs: list[ResearchBrief], event_id: str) -> list[Task]:
        """The fan-out tasks: compiled briefs where available, plan seeds everywhere else."""
        briefs_by_category = {brief.category: brief for brief in briefs}
        # sourcing_tasks iterates plan.vendor_categories, so the two zip in step.
        tasks = sourcing_tasks(plan, event_id)
        for task, category in zip(tasks, plan.vendor_categories):
            brief = briefs_by_category.get(category.category)
            if brief is not None:
                task.title = _render_research_brief(brief, category.budget_usd)
        return tasks

    async def _synthesize(self, plan: EventPlan, tasks: list[Task], runs: list[TaskRun]) -> SessionResult:
        blocks = [f"Event: {plan.event_summary}"]
        caps = [
            f"- {category.category}: ${category.budget_usd:.0f}"
            for category in plan.vendor_categories
            if category.budget_usd is not None
        ]
        if caps:
            blocks.append("Budget caps:\n" + "\n".join(caps))
        for task, run in zip(tasks, runs):
            category = task.assignee_agent
            if run.result.succeeded and run.result.data is not None:
                blocks.append(f"{category} research (JSON):\n{json.dumps(run.result.data)}")
            else:
                # The failure must be model-visible so it lands in gaps, not silence.
                reason = run.result.error or run.result.status
                blocks.append(f"{category} research: RESEARCH FAILED: {reason}")
        return await complete("\n\n".join(blocks), SHORTLIST_INSTRUCTIONS, VendorShortlist, http_client=self._http)


def _render_research_brief(brief: ResearchBrief, budget_usd: float | None) -> str:
    lines = [
        f"Goal: {brief.objective}",
        f"Start at: {brief.start_url}",
        "Steps:",
        *[f"{number}. {step}" for number, step in enumerate(brief.steps, 1)],
    ]
    if brief.constraints:
        lines.append("Constraints:")
        lines.extend(f"- {constraint}" for constraint in brief.constraints)
    lines.append(f"Success criteria: {brief.success_criteria}")
    return "\n".join(lines + research_guards(budget_usd))
