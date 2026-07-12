"""Agent orchestrator — selects the correct agent for each task.

Selection is explicit when the task already names its agent; otherwise a fast Holo
completion routes it across the roster — the domain fleet plus H's managed read-only
agents for general web work no specialist owns. Dispatch fans out as independent
top-level H sessions grouped per event: at capacity H queues top-level sessions but
fails subagent children with 429, so client-side fan-out over top-level sessions is
the shape the platform rewards (hub.hcompany.ai/computer-use-agents/multi-agent).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import httpx
from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from agents.budget_agent import BudgetAgent
from agents.catering_agent import CateringAgent
from agents.decorations_agent import DecorationsAgent
from agents.distribution_agent import DistributionAgent
from agents.entertainment_agent import EntertainmentAgent
from agents.marketing_agent import MarketingAgent
from agents.merchandise_agent import MerchandiseAgent
from agents.post_event_agent import PostEventAgent
from agents.purchasing_agent import PurchasingAgent
from agents.requirements_agent import RequirementsAgent
from agents.scheduling_agent import SchedulingAgent
from agents.staffing_agent import StaffingAgent
from agents.venue_agent import VenueAgent
from core.config import settings
from integrations.h_company.client import HClient, run_structured_completion
from integrations.h_company.schemas import DEFAULT_AGENT, MODEL_FAST, SessionResult
from models.task import Task

# The domain fleet, in event-lifecycle order — also the order the router reads it in.
_AGENT_CLASSES: tuple[type[BaseAgent], ...] = (
    RequirementsAgent,
    VenueAgent,
    CateringAgent,
    StaffingAgent,
    EntertainmentAgent,
    DecorationsAgent,
    MerchandiseAgent,
    PurchasingAgent,
    SchedulingAgent,
    BudgetAgent,
    MarketingAgent,
    DistributionAgent,
    PostEventAgent,
)

DOMAIN_AGENTS: dict[str, type[BaseAgent]] = {cls.name: cls for cls in _AGENT_CLASSES}

# H's managed read-only agents, for tasks no specialist owns. Their routing descriptions
# live here because the router is their only consumer. The pro variants are deliberately
# absent: flash covers the same roles faster, and deep multi-step work is what the domain
# specialists above exist for.
BUILTIN_AGENTS: dict[str, str] = {
    DEFAULT_AGENT: "General interactive web tasks that fit no specialist above.",
    "h/web-scraper-flash": "Reads and extracts content from already-known pages; no interaction.",
    "h/deep-search-pro": "Broad multi-source research questions needing a cited, synthesized answer.",
}

ROSTER_NAMES: frozenset[str] = frozenset(DOMAIN_AGENTS) | frozenset(BUILTIN_AGENTS)

# Managed agents carry no per-agent run bounds, and an unbounded session would pin its
# fan-out slot indefinitely (see HClient.run_task), so cap them like a mid-tier domain run.
BUILTIN_MAX_TIME_S = 1200.0

_ROSTER = "\n".join(
    [f"- {cls.name}: {cls.description}" for cls in _AGENT_CLASSES]
    + [f"- {agent_id}: {text}" for agent_id, text in BUILTIN_AGENTS.items()]
)

ROUTING_INSTRUCTIONS = f"""\
You route event-planning tasks to the single best agent on Occasion's roster.

Agents:
{_ROSTER}

Rules:
- Pick the one agent whose specialty matches the task's primary action.
- Prefer a specialist over the h/ agents; use those only for general web work no
  specialist owns: h/web-scraper-flash to read a known page, h/deep-search-pro for
  broad research, h/web-surfer-flash for any other general browsing.
- Completing a purchase or checkout always belongs to purchasing.
- Answer with the chosen agent's exact name as listed."""


class RouteDecision(BaseModel):
    """The router's verdict on where a task belongs.

    `reason` is declared first so constrained decoding makes the model justify the
    choice before it commits to a name.
    """

    reason: str = Field(description="One sentence on why the chosen agent fits the task.")
    agent: str = Field(description="The chosen agent's exact name from the roster.")


class TaskRun(BaseModel):
    """One orchestrated run: which agent took the task, why, and what came back.

    `agent` is None when the task never reached an agent — routing failed, or an explicit
    assignee was unknown — and the result's error says why. `reason` is the router's
    rationale; it stays None when the assignment was explicit.
    """

    task_id: str | None = None
    agent: str | None = None
    reason: str | None = None
    result: SessionResult


class Orchestrator:
    """Routes each task to the right fleet member and runs it as an H session.

    `client` backs browser sessions (domain agents and H's managed agents); `http_client`
    backs Models API calls (routing and the requirements agent). Both default to real
    settings-backed clients; tests inject fakes through the same seams the agents expose.
    """

    def __init__(self, client: HClient | None = None, http_client: httpx.Client | None = None) -> None:
        self._client = client
        self._http = http_client

    async def run_task(self, task: str | Task) -> TaskRun:
        """Run one task on the best agent, recording a routed choice on the Task itself."""
        assigned = task.assignee_agent if isinstance(task, Task) else None
        if assigned:
            if assigned not in ROSTER_NAMES:
                # An explicit assignment we can't honor is a caller bug; rerouting would hide it.
                return TaskRun(task_id=_task_id(task), result=_error(f"unknown assignee_agent {assigned!r}"))
            name, reason = assigned, None
        else:
            routed = await self._route(task)
            if isinstance(routed, SessionResult):  # routing itself failed; the result says why
                return TaskRun(task_id=_task_id(task), result=routed)
            name, reason = routed.agent, routed.reason
            if name not in ROSTER_NAMES:
                # Constrained decoding can still hallucinate a label; the general agent is the safe floor.
                name, reason = DEFAULT_AGENT, f"router named unknown agent {routed.agent!r}"
            if isinstance(task, Task):
                # The decision belongs on the domain object; a re-run then skips the router.
                task.assignee_agent = name
        result = await self._dispatch(name, task)
        return TaskRun(task_id=_task_id(task), agent=name, reason=reason, result=result)

    async def run_tasks(self, tasks: Sequence[str | Task], *, limit: int = 3) -> list[TaskRun]:
        """Run many tasks as independent top-level sessions, at most `limit` at a time.

        The default matches H's free-tier concurrent-session slots; sessions queued
        server-side still burn their max_time_s waiting, so the cap stays client-side.
        Results keep the input order.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")
        gate = asyncio.Semaphore(limit)

        async def run_gated(task: str | Task) -> TaskRun:
            async with gate:
                return await self.run_task(task)

        return list(await asyncio.gather(*(run_gated(task) for task in tasks)))

    async def _route(self, task: str | Task) -> RouteDecision | SessionResult:
        """Pick from the roster with the fast model; an error result means routing failed.

        The completion call blocks, so it runs in a worker thread like every H call.
        """
        routing = await asyncio.to_thread(
            run_structured_completion,
            _task_text(task),
            ROUTING_INSTRUCTIONS,
            RouteDecision,
            model=MODEL_FAST,
            http_client=self._http,
        )
        if not routing.succeeded:
            return routing
        return RouteDecision.model_validate(routing.data)

    async def _dispatch(self, name: str, task: str | Task) -> SessionResult:
        """Run the task on the named fleet member; failures come back as results."""
        if name in DOMAIN_AGENTS:
            agent_class = DOMAIN_AGENTS[name]
            if agent_class is RequirementsAgent:
                # The one browserless agent — it talks to the Models API, not a browser.
                return await RequirementsAgent(http_client=self._http).run(task)
            return await agent_class(client=self._client).run(task)
        return await self._run_builtin(name, task)

    async def _run_builtin(self, agent_id: str, task: str | Task) -> SessionResult:
        """Run the task on one of H's managed agents, bounded and grouped like domain runs.

        Passing the agent as a string makes HClient apply the browser overrides, so the
        managed agent gets the same signed-in cloud Chrome the domain agents use.
        """
        if not settings.hai_api_key:
            return _error("HAI_API_KEY is not configured; set it in services/agent/.env")
        client = self._client or HClient.from_settings()
        return await asyncio.to_thread(
            client.run_task,
            _task_text(task),
            agent_id,
            max_time_s=BUILTIN_MAX_TIME_S,
            group_id=task.event_id if isinstance(task, Task) else None,
        )


def _task_text(task: str | Task) -> str:
    # Mirrors BaseAgent.build_prompt so the router reads exactly what the agent will.
    return f"{task.title} (event: {task.event_id})" if isinstance(task, Task) else task


def _task_id(task: str | Task) -> str | None:
    return task.id if isinstance(task, Task) else None


def _error(message: str) -> SessionResult:
    return SessionResult(succeeded=False, status="error", error=message)
