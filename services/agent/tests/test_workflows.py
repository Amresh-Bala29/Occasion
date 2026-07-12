"""Tests for the three sequential workflows: planning, sourcing, and outreach.

Nothing here talks to H. Browser sessions run against a fake SDK injected through
HClient whose presets are keyed by message content — run_tasks fans out across
threads, so call *order* is not deterministic but content matching is. The Models
API is faked with an httpx MockTransport that serves scripted responses strictly
in order: workflow completions are sequential, so call order is part of the
contract under test.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

# Make the agent service root importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings  # noqa: E402
from core.orchestrator import BUILTIN_MAX_TIME_S, DOMAIN_AGENTS, Orchestrator, TaskRun  # noqa: E402
from integrations.h_company.client import HClient  # noqa: E402
from integrations.h_company.schemas import SessionResult  # noqa: E402
from models.task import Task  # noqa: E402
from workflows.event_planning import (  # noqa: E402
    PLAN_INSTRUCTIONS,
    SOURCEABLE_CATEGORIES,
    EventPlan,
    EventPlanningWorkflow,
    VendorCategoryPlan,
    sourcing_tasks,
)
from workflows.vendor_outreach import (  # noqa: E402
    OutreachDraft,
    OutreachReport,
    QuoteComparison,
    VendorOutreachWorkflow,
)
from workflows.vendor_sourcing import VendorCandidate, VendorShortlist, VendorSourcingWorkflow  # noqa: E402


class FakeSDK:
    """Stands in for hai_agents.Client: serves presets keyed by message content.

    `routes` are (needle, result) pairs matched against the session's message,
    first hit wins; `default` covers everything else. Content keying keeps results
    deterministic under run_tasks' concurrent fan-out, where call order is not.
    """

    def __init__(self, default: object | None = None, routes: list[tuple[str, object]] | None = None) -> None:
        self._default = default
        self._routes = routes or []
        self._lock = threading.Lock()
        self.calls: list[dict] = []

    def run_session(self, **kwargs) -> object:
        with self._lock:
            self.calls.append(kwargs)
        for needle, result in self._routes:
            if needle in kwargs["messages"]:
                return result
        assert self._default is not None, f"no scripted result for message: {kwargs['messages'][:80]!r}"
        return self._default

    def call_for(self, needle: str) -> dict:
        return next(call for call in self.calls if needle in call["messages"])


def fake_result(**fields) -> SimpleNamespace:
    """A SessionRunResult look-alike; unset fields default to None."""
    defaults = {"id": None, "status": None, "outcome": None, "answer": None, "error": None, "error_code": None}
    return SimpleNamespace(**{**defaults, **fields})


def browser_success(answer: object = "done") -> SimpleNamespace:
    # Mirrors a real settled single-shot run: status 'idle' with outcome 'success'.
    return fake_result(status="idle", outcome="success", answer=answer)


def browser_failure(error: str = "session crashed") -> SimpleNamespace:
    return fake_result(status="failed", error=error)


def browser_partial(answer: object) -> SimpleNamespace:
    # A run that settled with findings but self-assessed as incomplete (AGP does this).
    return fake_result(status="idle", outcome="partial", answer=answer)


class FakeResearch(BaseModel):
    """Stands in for a domain agent's answer schema; only its `.data` dump matters."""

    options: list[dict] = []


class FakeActResearch(BaseModel):
    """An entertainment-shaped answer: acts under act_name, plus a recommendation."""

    options: list[dict] = []
    recommended: str | None = None


class FakeStaffingResearch(BaseModel):
    """A staffing-shaped answer: candidates keyed by role/source, no options list."""

    candidates: list[dict] = []


def completion_script(*entries: dict | int) -> tuple[httpx.Client, list[httpx.Request]]:
    """A sequenced Models API double: a dict serves a 200 completion, an int that HTTP status."""
    remaining = list(entries)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert remaining, "workflow made more completion calls than the test scripted"
        entry = remaining.pop(0)
        if isinstance(entry, int):
            return httpx.Response(entry, text="scripted failure")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(entry)}}]})

    return httpx.Client(transport=httpx.MockTransport(respond)), requests


def request_text(request: httpx.Request, part: int = 1) -> str:
    return json.loads(request.content)["messages"][part]["content"]


def requirements_content() -> dict:
    return {"event_type": "conference", "date": "2026-09-10", "location": "Austin, TX", "headcount": 150, "budget_usd": 20000}


def plan_content() -> dict:
    return {
        "event_summary": "A 150-person conference in Austin, TX on 2026-09-10.",
        "vendor_categories": [
            {"category": "venue", "requirements_summary": "Seated capacity for 150 with AV.", "budget_usd": 8000},
            {"category": "catering", "requirements_summary": "Lunch for 150 with vegetarian options.", "budget_usd": 6000},
        ],
        "key_deadlines": [
            {"date": "2026-08-10", "title": "Sign venue contract", "consequence": "Preferred venues release the date"},
            {"date": "2026-09-01", "title": "Final catering headcount"},
        ],
    }


def make_plan() -> EventPlan:
    return EventPlan.model_validate(plan_content())


def briefs_content() -> dict:
    return {
        "briefs": [
            {
                "category": "venue",
                "objective": "Find five Austin venues seating 150",
                "start_url": "https://www.peerspace.com/austin",
                "steps": ["Filter capacity to 150", "Verify price and availability on each listing"],
                "success_criteria": "Five venues with capacity, price, and availability verified on the page",
                "constraints": ["Date 2026-09-10", "Budget $8000"],
            },
            {
                "category": "catering",
                "objective": "Find caterers for 150 with vegetarian options",
                "start_url": "https://www.google.com/search?q=austin+corporate+catering",
                "steps": ["Open the top caterer sites", "Verify per-person pricing on their menus"],
                "success_criteria": "Four caterers with per-person pricing verified",
                "constraints": ["Headcount 150"],
            },
        ]
    }


def shortlist_content() -> dict:
    return {
        "candidates": [
            {
                "category": "venue",
                "name": "The Grand Hall",
                "url": "https://grandhall.example.com",
                "contact_path": "https://grandhall.example.com/contact",
                "price_notes": "$7,500 full day",
                "availability": "2026-09-10 open",
                "rank": 1,
            },
            {"category": "venue", "name": "Riverside Loft", "url": "https://riversideloft.example.com", "rank": 2},
            {
                "category": "catering",
                "name": "Verde Catering",
                "url": "https://verdecatering.example.com",
                "contact_path": "quotes@verdecatering.example.com",
                "rank": 1,
            },
            {"category": "catering", "name": "Smoke & Oak BBQ", "url": "https://smokeoak.example.com", "rank": 2},
        ]
    }


def make_shortlist() -> VendorShortlist:
    return VendorShortlist.model_validate(shortlist_content())


def drafts_content() -> dict:
    return {
        "drafts": [
            {
                "vendor_name": "The Grand Hall",
                "subject": "Availability for Sept 10 conference",
                "message": "Hello Grand Hall team, we are planning a 150-person conference on 2026-09-10.",
            },
            {"vendor_name": "Riverside Loft", "subject": "Venue inquiry — Sept 10", "message": "Hello Riverside Loft team."},
            {"vendor_name": "Verde Catering", "subject": "Catering quote for 150", "message": "Hello Verde team."},
            {"vendor_name": "Smoke & Oak BBQ", "subject": "Catering inquiry", "message": "Hello Smoke & Oak team."},
        ]
    }


def comparison_content() -> dict:
    return {
        "quotes": [
            {"vendor_name": "The Grand Hall", "category": "venue", "contacted": True, "channel": "form"},
        ],
        "escalations": [
            {"decision": "Approve the $7,500 Grand Hall quote?", "context": "Under the $8,000 venue budget."},
        ],
        "follow_ups_needed": ["Riverside Loft"],
    }


def make_outreach_report() -> OutreachReport:
    """A completed first round: three sends landed, Smoke & Oak's failed."""
    candidates = [VendorCandidate.model_validate(item) for item in shortlist_content()["candidates"]]
    drafts = [OutreachDraft.model_validate(item) for item in drafts_content()["drafts"]]
    send_runs = [
        TaskRun(result=SessionResult(succeeded=True, status="idle", outcome="success", answer="sent")),
        TaskRun(result=SessionResult(succeeded=True, status="idle", outcome="success", answer="sent")),
        TaskRun(result=SessionResult(succeeded=True, status="idle", outcome="success", answer="sent")),
        TaskRun(result=SessionResult(succeeded=False, status="failed", error="send crashed")),
    ]
    return OutreachReport(
        event_id="evt-9",
        candidates=candidates,
        drafts=drafts,
        send_runs=send_runs,
        comparison=QuoteComparison.model_validate(comparison_content()),
        succeeded=True,
    )


def test_sourceable_categories_cover_the_agent_roster() -> None:
    # Category names double as agent names, so each one must be dispatchable...
    assert set(SOURCEABLE_CATEGORIES) <= set(DOMAIN_AGENTS)
    # ...and accepted by the category Literal that every plan and candidate uses.
    for category in SOURCEABLE_CATEGORIES:
        VendorCategoryPlan(category=category, requirements_summary="x")


def test_planning_happy_path_is_browserless(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK()
    http, requests = completion_script(requirements_content(), plan_content())
    flow = EventPlanningWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run("We want a 150-person conference in Austin.", event_id="evt-9"))

    assert report.succeeded is True
    assert sdk.calls == []  # planning opens no browser unless asked to schedule
    assert report.requirements.headcount == 150
    assert report.plan.event_summary.startswith("A 150-person conference")
    assert [task.id for task in report.sourcing_tasks] == ["evt-9-source-venue", "evt-9-source-catering"]
    assert [task.assignee_agent for task in report.sourcing_tasks] == ["venue", "catering"]
    for task in report.sourcing_tasks:
        assert "do not contact vendors, book, or pay anything" in task.title
    assert "Budget cap for this category: $8000" in report.sourcing_tasks[0].title
    # Sequential contract: the requirements agent first, then the plan synthesis.
    assert len(requests) == 2
    assert "We want a 150-person conference" in request_text(requests[0])
    assert request_text(requests[1], part=0) == PLAN_INSTRUCTIONS
    assert "Client brief:" in request_text(requests[1])
    assert "Today's date:" in request_text(requests[1])


def test_planning_requirements_failure_aborts(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    http, requests = completion_script(500)
    flow = EventPlanningWorkflow(client=HClient(FakeSDK()), http_client=http)

    report = asyncio.run(flow.run("Plan something", event_id="evt-9"))

    assert report.succeeded is False
    assert report.requirements is None
    assert report.requirements_run.result.error
    assert report.plan_run is None  # the gate stopped the workflow
    assert report.sourcing_tasks == []
    assert len(requests) == 1


def test_planning_synthesis_failure_returns_partial_report(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    http, _ = completion_script(requirements_content(), 500)
    flow = EventPlanningWorkflow(client=HClient(FakeSDK()), http_client=http)

    report = asyncio.run(flow.run("Plan something", event_id="evt-9"))

    assert report.succeeded is False
    assert report.requirements is not None  # stage 1 survived and stays readable
    assert report.plan is None
    assert report.plan_run.error
    assert report.sourcing_tasks == []


def test_planning_schedules_deadlines_when_asked(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_success("2 entries created"))
    http, _ = completion_script(requirements_content(), plan_content())
    flow = EventPlanningWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run("Conference brief", event_id="evt-9", schedule_deadlines=True))

    (call,) = sdk.calls
    assert call["agent"]["name"] == "occasion-scheduling"
    assert call["group_id"] == "evt-9"
    assert "Sign venue contract" in call["messages"]
    assert report.calendar_run.result.succeeded is True
    assert report.succeeded is True


def test_planning_calendar_failure_keeps_plan_success(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_failure("calendar unreachable"))
    http, _ = completion_script(requirements_content(), plan_content())
    flow = EventPlanningWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run("Conference brief", event_id="evt-9", schedule_deadlines=True))

    assert report.calendar_run.result.succeeded is False
    # The plan itself exists and calendar entries are reversible, so this stays a success.
    assert report.succeeded is True


def test_sourcing_tasks_seed_briefs_stand_alone() -> None:
    tasks = sourcing_tasks(make_plan(), "evt-9")

    assert [task.id for task in tasks] == ["evt-9-source-venue", "evt-9-source-catering"]
    assert [task.assignee_agent for task in tasks] == ["venue", "catering"]
    venue = tasks[0]
    assert "150-person conference in Austin" in venue.title  # event facts travel with the task
    assert "Seated capacity for 150" in venue.title
    assert "Budget cap for this category: $8000" in venue.title
    assert "do not contact vendors, book, or pay anything" in venue.title


def test_sourcing_happy_path_compiles_briefs_and_shortlists(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(
        routes=[
            ("peerspace", browser_success(FakeResearch(options=[{"name": "The Grand Hall"}]))),
            ("corporate+catering", browser_success(FakeResearch(options=[{"name": "Verde Catering"}]))),
        ]
    )
    http, requests = completion_script(briefs_content(), shortlist_content())
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_plan(), event_id="evt-9"))

    assert report.succeeded is True
    assert len(report.briefs) == 2
    assert {call["agent"]["name"] for call in sdk.calls} == {"occasion-venue", "occasion-catering"}
    venue_call = sdk.call_for("peerspace")
    assert "Start at: https://www.peerspace.com/austin" in venue_call["messages"]
    assert "Filter capacity to 150" in venue_call["messages"]
    assert "Budget cap for this category: $8000" in venue_call["messages"]
    assert "do not contact vendors, book, or pay anything" in venue_call["messages"]
    # The synthesis saw the research JSON, and the shortlist came back typed.
    assert "The Grand Hall" in request_text(requests[-1])
    assert report.shortlist.candidates[0].name == "The Grand Hall"
    assert len(report.research_runs) == len(report.research_tasks) == 2


def test_sourcing_compiler_failure_falls_back_to_seed_briefs(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_success(FakeResearch()))
    http, _ = completion_script(500, shortlist_content())
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_plan(), event_id="evt-9"))

    assert report.briefs_run.succeeded is False
    assert report.briefs == []
    # Brief compilation only enhances: the run proceeds on the plan's seed briefs.
    seeds = sourcing_tasks(make_plan(), "evt-9")
    assert [task.title for task in report.research_tasks] == [seed.title for seed in seeds]
    assert report.succeeded is True


def test_sourcing_research_failure_becomes_model_visible_gap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(
        routes=[
            ("peerspace", browser_success(FakeResearch(options=[{"name": "The Grand Hall"}]))),
            ("corporate+catering", browser_failure("blocked by CAPTCHA")),
        ]
    )
    http, requests = completion_script(briefs_content(), shortlist_content())
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_plan(), event_id="evt-9"))

    assert report.research_runs[1].result.succeeded is False
    synthesis_prompt = request_text(requests[-1])
    assert "RESEARCH FAILED" in synthesis_prompt
    assert "blocked by CAPTCHA" in synthesis_prompt
    assert report.succeeded is True  # the shortlist still parsed, gap and all


def test_sourcing_partial_research_with_data_feeds_synthesis(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(
        routes=[
            ("peerspace", browser_partial(FakeResearch(options=[{"name": "The Grand Hall"}]))),
            ("corporate+catering", browser_success(FakeResearch(options=[{"name": "Verde Catering"}]))),
        ]
    )
    http, requests = completion_script(briefs_content(), shortlist_content())
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_plan(), event_id="evt-9"))

    assert report.research_runs[0].result.succeeded is False  # partial is still not a success
    synthesis_prompt = request_text(requests[-1])
    assert "venue research (JSON, incomplete: partial)" in synthesis_prompt
    assert "The Grand Hall" in synthesis_prompt  # the partial run's findings made it in
    assert "RESEARCH FAILED" not in synthesis_prompt
    assert report.succeeded is True


def test_sourcing_retries_an_empty_shortlist_once(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_success(FakeResearch(options=[{"name": "The Grand Hall"}])))
    http, requests = completion_script(briefs_content(), {"candidates": []}, shortlist_content())
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_plan(), event_id="evt-9"))

    assert len(requests) == 3  # briefs, empty shortlist, retried shortlist
    assert report.succeeded is True
    assert report.shortlist.candidates


def test_sourcing_empty_shortlist_fails_with_enforced_gaps(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    # Optionless research: the code-built fallback has nothing to shortlist either.
    sdk = FakeSDK(default=browser_success(FakeResearch()))
    http, requests = completion_script(
        briefs_content(), {"candidates": []}, {"candidates": [], "next_steps": ["keep looking"]}
    )
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_plan(), event_id="evt-9"))

    assert len(requests) == 3  # the one retry was spent
    assert report.succeeded is False  # a tidy shortlist of nothing is still a failed round
    assert sorted(report.shortlist.gaps) == [
        "catering: research found no viable candidates",
        "venue: research found no viable candidates",
    ]


def test_sourcing_falls_back_to_code_built_shortlist_when_synthesis_drops_findings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(
        routes=[
            (
                "peerspace",
                browser_success(
                    FakeResearch(
                        options=[
                            {
                                "name": "The Grand Hall",
                                "url": "https://grandhall.example.com",
                                "price_notes": "$7,500 full day",
                                "availability": "2026-09-10 open",
                                "contact_path": "https://grandhall.example.com/contact",
                                "pros": ["Seats 180", "AV included"],
                            },
                            {"name": "Riverside Loft", "url": "https://riversideloft.example.com"},
                        ]
                    )
                ),
            ),
            (
                "corporate+catering",
                browser_success(
                    FakeResearch(
                        options=[
                            {
                                "name": "Verde Catering",
                                "url": "https://verdecatering.example.com",
                                "price_per_person": "$38/person",
                                "contact_path": "quotes@verdecatering.example.com",
                            }
                        ]
                    )
                ),
            ),
        ]
    )
    # The synthesis returns nothing twice; the findings must still become a shortlist.
    http, requests = completion_script(briefs_content(), {"candidates": []}, {"candidates": []})
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_plan(), event_id="evt-9"))

    assert len(requests) == 3  # briefs, empty shortlist, retried shortlist
    assert report.succeeded is True
    assert report.shortlist.gaps == []
    grand_hall, riverside, verde = report.shortlist.candidates
    assert (grand_hall.category, grand_hall.rank) == ("venue", 1)
    assert grand_hall.price_notes == "$7,500 full day"
    assert grand_hall.availability == "2026-09-10 open"
    assert grand_hall.contact_path == "https://grandhall.example.com/contact"
    assert grand_hall.fit_rationale == "Seats 180; AV included"
    assert (riverside.name, riverside.rank) == ("Riverside Loft", 2)
    assert (verde.category, verde.rank) == ("catering", 1)
    assert verde.price_notes == "$38/person"  # per-person pricing maps into price_notes
    # The audit record stays the real synthesis answer, not the code-built rescue.
    assert report.shortlist_run.data["candidates"] == []


def test_sourcing_fallback_survives_a_failed_synthesis_and_maps_act_name(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    plan = EventPlan.model_validate(
        {
            "event_summary": "A 150-person launch party.",
            "vendor_categories": [{"category": "entertainment", "requirements_summary": "A live act for 150."}],
        }
    )
    sdk = FakeSDK(
        default=browser_success(
            FakeActResearch(
                options=[{"act_name": "The Margarita Brothers", "url": "https://gigsalad.example.com/margarita"}],
                recommended="The Margarita Brothers",
            )
        )
    )
    http, requests = completion_script({"briefs": []}, 500)
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(plan, event_id="evt-9"))

    assert len(requests) == 2  # briefs, then the one synthesis attempt — no retry after a hard failure
    assert report.succeeded is True
    (act,) = report.shortlist.candidates
    assert (act.category, act.name) == ("entertainment", "The Margarita Brothers")
    assert act.fit_rationale == "Recommended by the entertainment research"
    assert report.shortlist_run.succeeded is False  # the failed synthesis stays on record


def test_sourcing_fallback_reads_the_staffing_answer_shape(monkeypatch) -> None:
    # Staffing answers {candidates: [...]} with role/source fields, not {options: [...]}
    # with name — the fallback must still rescue those findings.
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    plan = EventPlan.model_validate(
        {
            "event_summary": "A 150-person launch party.",
            "vendor_categories": [{"category": "staffing", "requirements_summary": "Two bartenders."}],
        }
    )
    sdk = FakeSDK(
        default=browser_success(
            FakeStaffingResearch(
                candidates=[
                    {
                        "role": "Bartender",
                        "source": "StaffedUp",
                        "url": "https://staffedup.example.com/bartenders",
                        "rate_notes": "$45/hr",
                        "availability": "Aug 15 evening",
                        "contact_path": "https://staffedup.example.com/contact",
                    }
                ]
            )
        )
    )
    http, _ = completion_script({"briefs": []}, 500)
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(plan, event_id="evt-9"))

    assert report.succeeded is True
    (candidate,) = report.shortlist.candidates
    assert (candidate.category, candidate.name) == ("staffing", "Bartender (StaffedUp)")
    assert candidate.price_notes == "$45/hr"
    assert candidate.contact_path == "https://staffedup.example.com/contact"


def test_sourcing_missing_category_gets_a_deterministic_gap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    venue_only = {"candidates": [c for c in shortlist_content()["candidates"] if c["category"] == "venue"]}
    sdk = FakeSDK(default=browser_success(FakeResearch()))
    http, _ = completion_script(briefs_content(), venue_only)
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_plan(), event_id="evt-9"))

    assert report.succeeded is True
    # The synthesis forgot catering; the gap is appended in code, not left to the model.
    assert report.shortlist.gaps == ["catering: research found no viable candidates"]


def test_sourcing_discovery_feeds_the_brief_compiler(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(
        default=browser_success(FakeResearch()),
        routes=[("Find candidate vendors", browser_success("Venue leads: https://www.peerspace.com/austin"))],
    )
    http, requests = completion_script(briefs_content(), shortlist_content())
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_plan(), event_id="evt-9", discover=True))

    discovery_call = sdk.call_for("Find candidate vendors")
    assert discovery_call["agent"] == "h/deep-search-pro"  # a string: the managed-agent path
    assert "overrides" in discovery_call
    assert discovery_call["max_time_s"] == BUILTIN_MAX_TIME_S
    # The sweep's answer lands in the compiler's context.
    assert "Venue leads: https://www.peerspace.com/austin" in request_text(requests[0])
    assert report.discovery_run.result.succeeded is True
    assert report.succeeded is True


def test_sourcing_synthesis_failure_preserves_research(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    # Optionless research keeps the fallback out of play; the failure must surface.
    sdk = FakeSDK(default=browser_success(FakeResearch()))
    http, _ = completion_script(briefs_content(), 500)
    flow = VendorSourcingWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_plan(), event_id="evt-9"))

    assert report.succeeded is False
    assert report.shortlist is None
    # The expensive browser findings survive the failed synthesis.
    assert len(report.research_runs) == 2
    assert all(run.result.data == {"options": []} for run in report.research_runs)


def test_book_embeds_approval_and_routes_to_the_specialist(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_success("booked"))
    flow = VendorSourcingWorkflow(client=HClient(sdk))
    candidate = VendorCandidate(
        category="venue",
        name="The Grand Hall",
        url="https://grandhall.example.com",
        availability="2026-09-10 open",
    )

    run = asyncio.run(
        flow.book(candidate, event_id="evt-9", approval="approved on 2026-07-11 for $7,500", budget_cap_usd=7500)
    )

    (call,) = sdk.calls
    assert call["agent"]["name"] == "occasion-venue"
    assert "The user has explicitly approved this booking: approved on 2026-07-11 for $7,500" in call["messages"]
    assert "Budget cap: $7500" in call["messages"]
    assert run.result.succeeded is True

    with pytest.raises(ValueError):
        asyncio.run(flow.book(candidate, event_id="evt-9", approval="   "))


def test_book_checkout_categories_route_to_purchasing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_success("ordered"))
    flow = VendorSourcingWorkflow(client=HClient(sdk))
    candidate = VendorCandidate(category="decorations", name="Party Depot", url="https://partydepot.example.com")

    asyncio.run(flow.book(candidate, event_id="evt-9", approval="approved: order the banner set"))

    (call,) = sdk.calls
    assert call["agent"]["name"] == "occasion-purchasing"


def test_outreach_happy_path_sends_via_the_web_agent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_success("Sent via contact form; confirmation banner shown"))
    http, _ = completion_script(drafts_content(), comparison_content())
    flow = VendorOutreachWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_shortlist(), event_id="evt-9", plan=make_plan()))

    assert report.succeeded is True
    assert len(report.send_runs) == 4  # two per category by default
    for call in sdk.calls:
        assert call["agent"] == "h/web-surfer-flash"  # never a domain agent: see module docstring
        assert "overrides" in call
        assert call["max_time_s"] == BUILTIN_MAX_TIME_S
        assert "Do not accept terms, sign anything, or pay anything." in call["messages"]
    grand_hall = sdk.call_for("The Grand Hall")
    assert "Subject: Availability for Sept 10 conference" in grand_hall["messages"]
    assert "we are planning a 150-person conference on 2026-09-10" in grand_hall["messages"]
    # An email contact path steers the run to Gmail instead of a form.
    verde = sdk.call_for("Verde Catering")
    assert "Start at: https://mail.google.com" in verde["messages"]
    assert "compose a new email to quotes@verdecatering.example.com" in verde["messages"]
    assert report.comparison.escalations[0].decision == "Approve the $7,500 Grand Hall quote?"


def test_outreach_honors_max_per_category(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_success("sent"))
    http, _ = completion_script(drafts_content(), comparison_content())
    flow = VendorOutreachWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_shortlist(), event_id="evt-9", max_per_category=1))

    # Only the rank-1 candidate of each category goes out.
    assert [task.id for task in report.send_tasks] == [
        "evt-9-outreach-the-grand-hall",
        "evt-9-outreach-verde-catering",
    ]


def test_outreach_draft_failure_falls_back_to_the_template(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_success("sent"))
    http, _ = completion_script(500, comparison_content())
    flow = VendorOutreachWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_shortlist(), event_id="evt-9", plan=make_plan()))

    assert report.drafts_run.succeeded is False
    # The round still goes out: a plain inquiry built from real facts beats silence.
    assert len(report.send_runs) == 4
    grand_hall = sdk.call_for("The Grand Hall")
    assert "Subject: Availability and quote request — The Grand Hall" in grand_hall["messages"]
    assert "itemized quote" in grand_hall["messages"]
    assert "A 150-person conference in Austin" in grand_hall["messages"]
    assert report.succeeded is True


def test_outreach_partial_draft_join_uses_template_for_the_missing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    partial = drafts_content()
    partial["drafts"] = [draft for draft in partial["drafts"] if draft["vendor_name"] != "Riverside Loft"]
    sdk = FakeSDK(default=browser_success("sent"))
    http, _ = completion_script(partial, comparison_content())
    flow = VendorOutreachWorkflow(client=HClient(sdk), http_client=http)

    asyncio.run(flow.run(make_shortlist(), event_id="evt-9", plan=make_plan()))

    # A vendor the model skipped degrades to the template instead of being dropped.
    riverside = sdk.call_for("Riverside Loft")
    assert "Subject: Availability and quote request — Riverside Loft" in riverside["messages"]
    grand_hall = sdk.call_for("The Grand Hall")
    assert "Subject: Availability for Sept 10 conference" in grand_hall["messages"]


def test_outreach_send_failure_flows_into_the_comparison(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(
        default=browser_success("sent"),
        routes=[("Riverside Loft", browser_failure("form rejected the submission"))],
    )
    http, requests = completion_script(drafts_content(), comparison_content())
    flow = VendorOutreachWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_shortlist(), event_id="evt-9"))

    comparison_prompt = request_text(requests[-1])
    assert "SEND FAILED" in comparison_prompt
    assert "form rejected the submission" in comparison_prompt
    assert report.succeeded is True  # other sends landed


def test_outreach_with_every_send_failed_is_not_success(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_failure("network down"))
    http, _ = completion_script(drafts_content(), comparison_content())
    flow = VendorOutreachWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.run(make_shortlist(), event_id="evt-9"))

    # A tidy comparison over zero contacts is still a failed round.
    assert report.comparison is not None
    assert report.succeeded is False


def test_follow_up_checks_the_thread_before_nudging(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    prior = make_outreach_report()
    nudges = {
        "drafts": [
            {"vendor_name": "Riverside Loft", "subject": "Venue inquiry — Sept 10", "message": "Checking in on our venue inquiry."},
            {"vendor_name": "Smoke & Oak BBQ", "subject": "Catering inquiry", "message": "Following up on our catering inquiry."},
        ]
    }
    sdk = FakeSDK(default=browser_success("no reply found; follow-up sent"))
    http, requests = completion_script(nudges, comparison_content())
    flow = VendorOutreachWorkflow(client=HClient(sdk), http_client=http)

    report = asyncio.run(flow.follow_up(prior, event_id="evt-9"))

    # Targets = the vendor the comparison flagged plus the one whose send failed.
    assert {task.id for task in report.send_tasks} == {
        "evt-9-followup-riverside-loft",
        "evt-9-followup-smoke-oak-bbq",
    }
    riverside = sdk.call_for("Riverside Loft")
    assert "search for the subject: Venue inquiry — Sept 10" in riverside["messages"]
    assert "Only if there is no reply" in riverside["messages"]
    assert "Checking in on our venue inquiry." in riverside["messages"]
    assert "never re-submit the form" in riverside["messages"]
    # The fresh comparison sees the prior one, so knowledge accumulates without a DB.
    assert "Prior comparison (JSON)" in request_text(requests[-1])
    assert report.succeeded is True


def test_follow_up_with_nothing_to_chase_keeps_the_prior_picture(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    prior = make_outreach_report()
    prior.comparison.follow_ups_needed = []
    prior.send_runs[3] = TaskRun(result=SessionResult(succeeded=True, status="idle", outcome="success", answer="sent"))
    sdk = FakeSDK()
    flow = VendorOutreachWorkflow(client=HClient(sdk), http_client=completion_script()[0])

    report = asyncio.run(flow.follow_up(prior, event_id="evt-9"))

    assert sdk.calls == []
    assert report.send_tasks == []
    assert report.comparison == prior.comparison
    assert report.succeeded is True


def test_negotiate_sends_a_propose_only_reply_in_thread(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    prior = make_outreach_report()
    counter = {
        "vendor_name": "The Grand Hall",
        "subject": "Availability for Sept 10 conference",
        "message": "Would you consider $7,000 including AV support?",
    }
    sdk = FakeSDK(default=browser_success("reply sent in thread"))
    http, _ = completion_script(counter)
    flow = VendorOutreachWorkflow(client=HClient(sdk), http_client=http)

    round_ = asyncio.run(flow.negotiate(prior, "The Grand Hall", event_id="evt-9", ask="Ask for $7,000 including AV"))

    (call,) = sdk.calls
    assert call["agent"] == "h/web-surfer-flash"
    assert "search for the subject: Availability for Sept 10 conference" in call["messages"]
    assert "Would you consider $7,000 including AV support?" in call["messages"]
    assert "Propose only — do not accept a counter-offer" in call["messages"]
    assert round_.message == "Would you consider $7,000 including AV support?"
    assert round_.send_run.result.succeeded is True

    with pytest.raises(ValueError):
        asyncio.run(flow.negotiate(prior, "Nobody Inc", event_id="evt-9", ask="anything"))


def test_orchestrator_runs_a_pinned_planning_workflow(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK()
    http, requests = completion_script(requirements_content(), plan_content())
    task = Task(
        id="t1",
        event_id="evt-9",
        title="We want a 150-person conference in Austin.",
        assignee_agent="workflow/event_planning",
    )

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task(task))

    assert run.agent == "workflow/event_planning"
    assert run.result.succeeded is True
    assert sdk.calls == []  # the planning chain is browserless
    assert run.result.answer == "A 150-person conference in Austin, TX on 2026-09-10."
    assert run.result.data["planning"]["plan"]["event_summary"] == run.result.answer
    # The raw title is the brief: the event suffix is added once, by the requirements task.
    assert request_text(requests[0]).count("(event: evt-9)") == 1
    assert len(requests) == 2  # requirements parse, then plan synthesis


def test_orchestrator_chains_planning_into_a_routed_sourcing_workflow(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(
        routes=[
            ("peerspace", browser_success(FakeResearch(options=[{"name": "The Grand Hall"}]))),
            ("corporate+catering", browser_success(FakeResearch(options=[{"name": "Verde Catering"}]))),
        ]
    )
    route = {"reason": "end-to-end vendor sourcing", "agent": "workflow/vendor_sourcing"}
    http, requests = completion_script(
        route, requirements_content(), plan_content(), briefs_content(), shortlist_content()
    )
    task = Task(id="t1", event_id="evt-9", title="Source vendors for our 150-person Austin conference.")

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task(task))

    assert task.assignee_agent == "workflow/vendor_sourcing"  # the routed decision is recorded
    assert run.reason == "end-to-end vendor sourcing"
    assert run.result.succeeded is True
    assert set(run.result.data) == {"planning", "sourcing"}
    assert {call["agent"]["name"] for call in sdk.calls} == {"occasion-venue", "occasion-catering"}
    assert run.result.answer == "Shortlisted 4 vendors across 2 categories; gaps: 0."
    assert len(requests) == 5  # route, requirements, plan, briefs, shortlist


def test_orchestrator_reports_an_empty_shortlist_honestly(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    # Optionless research: the code-built fallback can't rescue this round either.
    sdk = FakeSDK(default=browser_success(FakeResearch()))
    http, _ = completion_script(
        requirements_content(), plan_content(), briefs_content(), {"candidates": []}, {"candidates": []}
    )
    task = Task(id="t1", event_id="evt-9", title="Source vendors", assignee_agent="workflow/vendor_sourcing")

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task(task))

    assert run.result.succeeded is False
    # Not "did not succeed: completed" — the synthesis run finished; its content was the problem.
    assert run.result.error == "sourcing stage did not succeed: shortlist came back empty; gaps: 2"
    assert set(run.result.data) == {"planning", "sourcing"}  # the plan still rides along for publishing


def test_orchestrator_reports_stages_to_the_on_stage_hook(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_success(FakeResearch()))
    http, _ = completion_script(requirements_content(), plan_content(), briefs_content(), shortlist_content())
    task = Task(id="t1", event_id="evt-9", title="Source vendors", assignee_agent="workflow/vendor_sourcing")
    orchestrator = Orchestrator(client=HClient(sdk), http_client=http)
    seen: list[tuple[str, dict]] = []
    orchestrator.on_stage = lambda stage, payload: seen.append((stage, payload))

    run = asyncio.run(orchestrator.run_task(task))

    assert run.result.succeeded is True
    assert [stage for stage, _ in seen] == ["planning", "sourcing"]
    assert seen[0][1]["plan"]["event_summary"] == plan_content()["event_summary"]
    assert seen[1][1]["shortlist"]["candidates"]


def test_orchestrator_survives_a_raising_on_stage_hook(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(default=browser_success(FakeResearch()))
    http, _ = completion_script(requirements_content(), plan_content(), briefs_content(), shortlist_content())
    task = Task(id="t1", event_id="evt-9", title="Source vendors", assignee_agent="workflow/vendor_sourcing")
    orchestrator = Orchestrator(client=HClient(sdk), http_client=http)

    def explode(stage: str, payload: dict) -> None:
        raise RuntimeError("publish hook blew up")

    orchestrator.on_stage = explode

    run = asyncio.run(orchestrator.run_task(task))

    assert run.result.succeeded is True  # the observer must never fail the workflow


def test_orchestrator_workflow_chain_stops_at_a_failed_gate(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK()
    http, requests = completion_script(500)
    task = Task(id="t1", event_id="evt-9", title="Source vendors", assignee_agent="workflow/vendor_sourcing")

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task(task))

    assert run.result.succeeded is False
    assert run.result.error.startswith("planning stage did not succeed: ")
    assert "500" in run.result.error  # the underlying failure travels up
    assert set(run.result.data) == {"planning"}  # nothing downstream ran
    assert sdk.calls == []
    assert len(requests) == 1


def test_orchestrator_runs_the_full_outreach_chain(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(
        default=browser_success("Sent via contact form; confirmation banner shown"),
        routes=[
            ("peerspace", browser_success(FakeResearch(options=[{"name": "The Grand Hall"}]))),
            ("corporate+catering", browser_success(FakeResearch(options=[{"name": "Verde Catering"}]))),
        ],
    )
    http, requests = completion_script(
        requirements_content(),
        plan_content(),
        briefs_content(),
        shortlist_content(),
        drafts_content(),
        comparison_content(),
    )
    task = Task(
        id="t1",
        event_id="evt-9",
        title="Get vendor quotes for our conference.",
        assignee_agent="workflow/vendor_outreach",
    )

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task(task))

    assert run.result.succeeded is True
    assert set(run.result.data) == {"planning", "sourcing", "outreach"}
    assert run.result.answer == "Contacted 4 of 4 shortlisted vendors; escalations for the user: 1."
    assert len(requests) == 6  # requirements, plan, briefs, shortlist, drafts, comparison
    # Research went to the category specialists; every send went to the general web agent.
    send_calls = [call for call in sdk.calls if call["agent"] == "h/web-surfer-flash"]
    assert len(send_calls) == 4
