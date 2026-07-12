"""Tests for the planning modules and the plan-persistence round-trip.

The transform classes are pure — they take the pipeline's EventPlan (plus an optional
BudgetReview / requirements and a fixed clock) and return detached ORM rows — so they're
asserted directly, no database. One round-trip test exercises save_plan against an
in-memory SQLite built over just the plan tables, checking the group→task flush and the
DTO read path without touching the real Postgres.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

# Make the agent service root importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@compiles(BigInteger, "sqlite")
def _sqlite_bigint_as_integer(_type, _compiler, **_kw):
    # SQLite only autoincrements an INTEGER PRIMARY KEY, not BIGINT; the identity PKs
    # (plan_phases, risks, …) rely on it. Postgres keeps its bigint identity untouched.
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _sqlite_jsonb_as_json(_type, _compiler, **_kw):
    # SQLite has no JSONB; the memory and run tables' JSON columns render as JSON here.
    return "JSON"

from agents.budget_agent import BudgetLine, BudgetReview  # noqa: E402
from agents.requirements_agent import EventRequirements  # noqa: E402
from core.config import settings  # noqa: E402
from core.orchestrator import TaskRun  # noqa: E402
from core.runs import RunManager  # noqa: E402
from database import models as orm  # noqa: E402
from database.repositories.event_repository import EventRepository  # noqa: E402
from database.repositories.memory_repository import MemoryRepository  # noqa: E402
from database.repositories.run_repository import RunRepository  # noqa: E402
from integrations.h_company.client import HClient  # noqa: E402
from integrations.h_company.schemas import SessionResult  # noqa: E402
from memory.event_memory import PLAN_SNAPSHOT, REQUIREMENTS, SHORTLIST  # noqa: E402
from planning.budget_optimizer import BudgetOptimizer  # noqa: E402
from planning.constraints import PlanningConstraints, parse_iso_date  # noqa: E402
from planning.risk_analyzer import RiskAnalyzer  # noqa: E402
from planning.schedule_optimizer import ScheduleOptimizer  # noqa: E402
from planning.task_graph import TaskGraph  # noqa: E402
from workflows.event_planning import (  # noqa: E402
    BudgetAllocation,
    ChecklistItem,
    EventPlan,
    KeyDeadline,
    PlanMilestone,
    RiskItem,
    VendorCategoryPlan,
)
from workflows.vendor_outreach import OutreachReport, QuoteComparison  # noqa: E402
from workflows.vendor_sourcing import VendorCandidate, VendorShortlist  # noqa: E402

TODAY = date(2026, 7, 11)


def _sample_plan() -> EventPlan:
    return EventPlan(
        event_summary="A 320-person summit at Pier 27 on Aug 6, 2026.",
        timeline=[
            PlanMilestone(date="2026-07-02", title="Requirements captured"),
            PlanMilestone(date="2026-08-06", title="Event day"),
            PlanMilestone(date="pending", title="Catering signed"),
        ],
        budget=[
            BudgetAllocation(category="Venue", estimated_usd=24_000.0),
            BudgetAllocation(category="Catering", estimated_usd=18_400.4),
            BudgetAllocation(category="Entertainment", estimated_usd=3_200.0),
        ],
        total_budget_usd=45_600.0,
        checklist=[
            ChecklistItem(title="Book Pier 27", category="venue", due="2026-07-08"),
            ChecklistItem(title="Research caterers", category="catering", due="2026-07-01"),
            ChecklistItem(title="Finalize menu", category="catering"),
            ChecklistItem(title="Order signage", category="signage"),
            ChecklistItem(title="Send thank-you notes", category="general"),
        ],
        vendor_categories=[VendorCategoryPlan(category="venue", requirements_summary="Book Pier 27 for Aug 6.")],
        key_deadlines=[KeyDeadline(date="2026-07-29", title="DJ deposit due")],
        risks=[
            RiskItem(risk="DJ not yet locked", likelihood="high", impact="high", mitigation="Hold a backup."),
            RiskItem(risk="Minor decor delay", likelihood="low", impact="low", mitigation="Order early."),
            RiskItem(risk="Rain risk", likelihood="high", impact="low", mitigation="Tent on standby."),
        ],
    )


# ---- constraints ----


def test_parse_iso_date():
    assert parse_iso_date("2026-08-06") == date(2026, 8, 6)
    assert parse_iso_date("pending") is None
    assert parse_iso_date("T-6 weeks") is None
    assert parse_iso_date("") is None
    assert parse_iso_date(None) is None


def test_constraints_from_requirements():
    constraints = PlanningConstraints.from_requirements(EventRequirements(budget_usd=50_000.0, date="2026-08-06"))
    assert constraints.budget_cap_usd == 50_000.0
    assert constraints.event_date == date(2026, 8, 6)
    assert constraints.over_budget_by(60_000) == 10_000.0
    assert constraints.over_budget_by(40_000) == 0.0
    assert constraints.days_to_event(TODAY) == 26

    capless = PlanningConstraints()
    assert capless.over_budget_by(999_999) == 0.0
    assert capless.days_to_event(TODAY) is None


# ---- risk analyzer ----


def test_risk_level_matrix_and_high_first():
    rows = RiskAnalyzer(_sample_plan(), constraints=PlanningConstraints(), today=TODAY).rows("e1")
    by_title = {r.title: r.level for r in rows}
    assert by_title["DJ not yet locked"] == "High"  # high × high
    assert by_title["Minor decor delay"] == "Low"  # low × low
    assert by_title["Rain risk"] == "Medium"  # high × low
    levels = [r.level for r in rows]
    assert levels == sorted(levels, key=["High", "Medium", "Low"].index)
    assert [r.ordinal for r in rows] == list(range(len(rows)))


def test_over_budget_adds_high_risk():
    rows = RiskAnalyzer(
        _sample_plan(), constraints=PlanningConstraints(budget_cap_usd=1_000.0), today=TODAY, over_budget_usd=5_000.0
    ).rows("e1")
    assert any("Budget over plan" in r.title and r.level == "High" for r in rows)


def test_budget_review_risks_folded_in():
    review = BudgetReview(lines=[], risks=["Catering trending over estimate"])
    rows = RiskAnalyzer(_sample_plan(), constraints=PlanningConstraints(), today=TODAY, budget_review=review).rows("e1")
    assert any(r.title == "Catering trending over estimate" and r.level == "Medium" for r in rows)


# ---- task graph ----


def test_checklist_groups_by_category():
    groups = {g.name: g for g in TaskGraph.from_plan(_sample_plan()).group_rows("e1")}
    assert groups["Venue & space"].owner == "Venue"
    assert groups["Venue & space"].tone == "blue"
    assert "Brand & decor" in groups  # signage -> decorations -> Brand & decor
    assert groups["Logistics"].owner == "Coordinator"  # "general" -> default group

    catering = groups["Food & beverage"]
    assert [t.label for t in catering.tasks] == ["Research caterers", "Finalize menu"]  # dated first
    assert catering.tasks[0].id == "e1-task-research-caterers"
    assert all(t.done is False for g in groups.values() for t in g.tasks)


def test_phase_rollup_and_percent_complete():
    graph = TaskGraph.from_plan(_sample_plan())
    phases = {p.name: p for p in graph.phase_rows("e1")}
    assert phases["Discovery"].percent == 100 and phases["Discovery"].note == "Done"
    assert phases["Sourcing"].note == "0 of 1"  # "Research caterers"
    assert phases["Booking"].note == "0 of 1"  # "Book Pier 27"
    assert phases["Production"].note == "0 of 2"  # "Order signage" + "Finalize menu" (default phase)
    assert phases["Wrap-up"].note == "0 of 1"  # "Send thank-you notes"
    assert phases["Day-of"].note == "Not started"
    assert graph.percent_complete() == 17  # only Discovery done, averaged across six phases


# ---- budget optimizer ----


def test_budget_from_allocations_all_estimates():
    budget = BudgetOptimizer(_sample_plan(), constraints=PlanningConstraints(budget_cap_usd=50_000.0)).build("e1")
    cats = {c.name: c for c in budget.categories}
    assert cats["Catering"].committed_usd == 18_400  # round(18_400.4)
    assert all(c.estimate is True and c.paid_usd == 0 for c in budget.categories)
    assert [c.name for c in budget.categories] == ["Venue", "Catering", "Entertainment"]  # largest first
    assert budget.total_usd == 50_000  # the cap is the ceiling
    assert budget.paid_usd == 0
    assert budget.pending_usd == 24_000 + 18_400 + 3_200
    assert budget.over_budget_usd == 0.0
    assert "under the $50,000 budget" in budget.footnote


def test_budget_from_review_aggregates_and_estimate_flag():
    review = BudgetReview(
        lines=[
            BudgetLine(category="Venue", confirmed_usd=24_000.0, paid_usd=12_000.0),
            BudgetLine(category="Catering", estimated_usd=18_000.0),
            BudgetLine(category="Catering", estimated_usd=400.0),
        ]
    )
    budget = BudgetOptimizer(_sample_plan(), constraints=PlanningConstraints(), review=review).build("e1")
    cats = {c.name: c for c in budget.categories}
    assert cats["Venue"].committed_usd == 24_000 and cats["Venue"].paid_usd == 12_000
    assert cats["Venue"].estimate is None  # has a confirmed figure
    assert cats["Catering"].committed_usd == 18_400  # two lines summed
    assert cats["Catering"].estimate is True  # no confirmed figure
    assert budget.total_usd == round(45_600.0)  # no cap -> the plan's own total
    assert budget.paid_usd == 12_000


def test_savings_amount_parsed():
    review = BudgetReview(lines=[], savings_suggestions=["Bundle rentals to save $490 on linens.", "Negotiate later."])
    savings = BudgetOptimizer(_sample_plan(), constraints=PlanningConstraints(), review=review).build("e1").savings
    assert savings[0].amount == "−$490"
    assert savings[0].note.startswith("Bundle rentals")
    assert savings[1].amount == ""  # no dollar figure to parse


# ---- schedule optimizer ----


def test_milestones_labels_order_and_done():
    rows = ScheduleOptimizer(_sample_plan()).rows("e1", today=TODAY)
    by_title = {m.title: m for m in rows}
    assert by_title["Requirements captured"].when == "Jul 2"
    assert by_title["Requirements captured"].done is True  # Jul 2 is before today
    assert by_title["Event day"].when == "Aug 6"
    assert by_title["Event day"].done is False
    assert by_title["Catering signed"].when == "pending"  # undated
    order = [m.title for m in rows]
    assert order.index("Requirements captured") < order.index("Event day")
    assert order[-1] == "Catering signed"  # undated sorts last
    assert [m.ordinal for m in rows] == list(range(len(rows)))


# ---- persistence round-trip ----


def _blank_event(event_id: str) -> orm.Event:
    return orm.Event(
        id=event_id, kind="", name="", short_name="", status_label="", date="", location="", headcount="",
        days_to_go="", percent_complete=0, total_usd=0, paid_usd=0, pending_usd=0, vendors_confirmed=0,
        vendors_total=0, vendors_in_progress=0, auto_approve_limit="", savings_footnote="",
    )


@pytest.fixture
def repo() -> EventRepository:
    engine = create_engine("sqlite://")

    @sa_event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):  # SQLite needs this on for ON DELETE CASCADE
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    tables = [
        orm.Event.__table__,
        orm.PlanPhase.__table__,
        orm.PlanTaskGroup.__table__,
        orm.PlanTask.__table__,
        orm.RiskItem.__table__,
        orm.Milestone.__table__,
        orm.BudgetCategory.__table__,
        orm.SavingSuggestion.__table__,
        orm.DeadlineItem.__table__,
        orm.Vendor.__table__,
        orm.ActivityItem.__table__,
        # The reconcile tests span runs and agent memory too.
        orm.AgentRunRow.__table__,
        orm.EventMemoryRow.__table__,
        orm.MemoryDocumentRow.__table__,
        orm.VendorReputationRow.__table__,
    ]
    orm.Base.metadata.create_all(engine, tables=tables)
    session = sessionmaker(bind=engine)()
    session.add(_blank_event("e1"))
    session.commit()
    return EventRepository(session)


def test_save_plan_round_trips_to_dtos(repo: EventRepository):
    review = BudgetReview(
        lines=[BudgetLine(category="Venue", confirmed_usd=24_000.0, paid_usd=12_000.0)],
        savings_suggestions=["Bundle rentals to save $490."],
    )
    requirements = EventRequirements(budget_usd=50_000.0, date="2026-08-06")
    repo.save_plan("e1", _sample_plan(), requirements=requirements, budget_review=review, today=TODAY)

    plan = repo.get_plan("e1")
    assert plan.phases[0].name == "Discovery" and plan.phases[0].percent == 100
    assert any(g.name == "Venue & space" for g in plan.groups)
    assert all(t.done is False for g in plan.groups for t in g.tasks)
    assert plan.risks and plan.risks[0].level == "High"
    assert any(m.title == "Event day" for m in plan.milestones)

    budget = repo.get_budget("e1")
    assert budget.categories[0].name == "Venue"  # largest commitment first
    assert budget.savings[0].amount == "−$490"

    deadlines = repo.get_key_deadlines("e1")
    assert [(d.month, d.day, d.title) for d in deadlines] == [("Jul", "29", "DJ deposit due")]

    event = repo.db.get(orm.Event, "e1")
    assert event.percent_complete == 17
    assert event.total_usd == 50_000
    assert event.paid_usd == 12_000
    assert event.pending_usd == 12_000  # committed 24,000 − paid 12,000
    assert event.days_to_go == "26 days"  # requirements date 2026-08-06 vs TODAY


def test_save_plan_is_idempotent(repo: EventRepository):
    repo.save_plan("e1", _sample_plan(), today=TODAY)
    repo.save_plan("e1", _sample_plan(), today=TODAY)
    plan = repo.get_plan("e1")
    assert sum(len(g.tasks) for g in plan.groups) == 5  # five checklist items, not doubled
    assert len(repo.get_key_deadlines("e1")) == 1  # key deadlines replaced, not doubled


def test_save_plan_days_to_go_falls_back_to_plan_date(repo: EventRepository):
    # "July 30" never ISO-parses; the plan's resolved date must carry the countdown.
    plan = _sample_plan().model_copy(update={"event_date": "2026-08-06"})
    repo.save_plan("e1", plan, requirements=EventRequirements(date="July 30"), today=TODAY)
    assert repo.db.get(orm.Event, "e1").days_to_go == "26 days"


def test_save_plan_without_parseable_date_leaves_days_to_go(repo: EventRepository):
    repo.save_plan("e1", _sample_plan(), today=TODAY)  # no requirements, no plan.event_date
    assert repo.db.get(orm.Event, "e1").days_to_go == ""  # untouched from _blank_event


# ---- vendor persistence ----


def _shortlist() -> VendorShortlist:
    return VendorShortlist(
        candidates=[
            VendorCandidate(category="venue", name="The Grand Pier", url="https://example.com/pier", rank=2),
            VendorCandidate(
                category="venue",
                name="Malibu West Beach Club",
                url="https://example.com/mwbc",
                price_notes="$3,950 evening rate",
                rank=1,
            ),
            VendorCandidate(category="catering", name="Coastal Catering Co", url="https://example.com/ccc", rank=1),
        ]
    )


def test_save_vendors_maps_shortlist_to_rows_and_counters(repo: EventRepository):
    repo.save_vendors("e1", _shortlist())

    vendors = repo.get_vendors("e1")
    # Ordered by (category, rank): catering's pick, then venue's pick, then the alternate.
    assert [v.name for v in vendors] == ["Coastal Catering Co", "Malibu West Beach Club", "The Grand Pier"]
    pick = vendors[1]
    assert pick.initials == "MW"
    assert pick.category == "Venue"
    assert pick.status == "Awaiting you"  # rank 1 waits on the user's decision
    assert pick.cost == "~$3,950"
    assert pick.quotes == 0
    assert vendors[2].status == "Sourcing"
    assert vendors[2].cost == "—"  # no price notes

    event = repo.db.get(orm.Event, "e1")
    assert (event.vendors_total, event.vendors_confirmed, event.vendors_in_progress) == (3, 0, 3)


def test_save_vendors_is_idempotent(repo: EventRepository):
    repo.save_vendors("e1", _shortlist())
    repo.save_vendors("e1", _shortlist())
    assert len(repo.get_vendors("e1")) == 3
    assert repo.db.get(orm.Event, "e1").vendors_total == 3


def test_confirm_vendor_flips_row_and_counters(repo: EventRepository):
    repo.save_vendors("e1", _shortlist())
    repo.confirm_vendor("e1", name="Malibu West Beach Club", amount_usd=3950.0)

    booked = next(v for v in repo.get_vendors("e1") if v.name == "Malibu West Beach Club")
    assert booked.status == "Confirmed"
    assert booked.cost == "$3,950"  # the approved amount, firm — no ~ estimate marker
    event = repo.db.get(orm.Event, "e1")
    assert (event.vendors_total, event.vendors_confirmed, event.vendors_in_progress) == (3, 1, 2)


def test_confirm_vendor_creates_a_missing_row(repo: EventRepository):
    # A booking off a memory shortlist that predates vendor persistence still lands.
    repo.confirm_vendor("e1", name="Pop-Up Tacos", category="catering", price_notes="around $1,200 all-in")

    (vendor,) = repo.get_vendors("e1")
    assert (vendor.name, vendor.category, vendor.status) == ("Pop-Up Tacos", "Catering", "Confirmed")
    assert vendor.cost == "$1,200"  # from the price notes when no approved amount exists
    event = repo.db.get(orm.Event, "e1")
    assert (event.vendors_total, event.vendors_confirmed, event.vendors_in_progress) == (1, 1, 0)


def test_save_outreach_marks_negotiating_and_lands_quotes(repo: EventRepository):
    repo.save_vendors("e1", _shortlist())
    comparison = QuoteComparison.model_validate(
        {
            "quotes": [
                {
                    "vendor_name": "Malibu West Beach Club",
                    "category": "venue",
                    "contacted": True,
                    "channel": "form",
                    "quoted_total_usd": 4200,
                }
            ]
        }
    )
    repo.save_outreach(
        "e1",
        contacted=["Malibu West Beach Club", "Coastal Catering Co", "Nobody Inc"],
        comparison=comparison,
    )

    vendors = {v.name: v for v in repo.get_vendors("e1")}
    quoted = vendors["Malibu West Beach Club"]
    assert (quoted.status, quoted.quotes, quoted.cost) == ("Negotiating", 1, "$4,200")
    assert vendors["Coastal Catering Co"].status == "Negotiating"  # contacted, no quote yet
    assert vendors["The Grand Pier"].status == "Sourcing"  # never contacted, untouched
    assert len(vendors) == 3  # "Nobody Inc" has no row and outreach must not invent one


def test_save_outreach_never_downgrades_a_confirmed_vendor(repo: EventRepository):
    repo.save_vendors("e1", _shortlist())
    repo.confirm_vendor("e1", name="Malibu West Beach Club")
    repo.save_outreach("e1", contacted=["Malibu West Beach Club"], comparison=None)

    booked = next(v for v in repo.get_vendors("e1") if v.name == "Malibu West Beach Club")
    assert booked.status == "Confirmed"


# ---- run -> dashboard publish bridge ----


def _workflow_run(stages: dict, *, succeeded: bool = True) -> TaskRun:
    return TaskRun(
        agent="workflow/vendor_sourcing",
        result=SessionResult(succeeded=succeeded, status="completed" if succeeded else "failed", data=stages),
    )


def test_publish_workflow_outputs_bridges_run_to_dashboard(repo: EventRepository):
    manager = RunManager(session_factory=lambda: repo.db)
    stages = {
        "planning": {
            "plan": _sample_plan().model_dump(mode="json"),
            "requirements": EventRequirements(budget_usd=50_000.0, date="2026-08-06").model_dump(mode="json"),
        },
        "sourcing": {"shortlist": _shortlist().model_dump(mode="json")},
    }
    manager._publish_workflow_outputs(_workflow_run(stages), "e1")

    assert repo.get_plan("e1").phases
    assert len(repo.get_vendors("e1")) == 3
    assert repo.db.get(orm.Event, "e1").total_usd == 50_000


def test_publish_persists_plan_even_off_a_failed_chain(repo: EventRepository):
    manager = RunManager(session_factory=lambda: repo.db)
    stages = {"planning": {"plan": _sample_plan().model_dump(mode="json"), "requirements": None}}
    manager._publish_workflow_outputs(_workflow_run(stages, succeeded=False), "e1")

    assert repo.get_plan("e1").phases  # the plan landed although sourcing never did
    assert repo.get_vendors("e1") == []


def test_publish_skips_empty_shortlist_to_protect_existing_vendors(repo: EventRepository):
    manager = RunManager(session_factory=lambda: repo.db)
    repo.save_vendors("e1", _shortlist())
    stages = {"sourcing": {"shortlist": {"candidates": [], "gaps": ["venue: research failed"]}}}
    manager._publish_workflow_outputs(_workflow_run(stages, succeeded=False), "e1")

    assert len(repo.get_vendors("e1")) == 3  # the earlier shortlist survives the failed round


def test_publish_ignores_non_workflow_runs(repo: EventRepository):
    manager = RunManager(session_factory=lambda: repo.db)
    run = TaskRun(
        agent="requirements",
        result=SessionResult(
            succeeded=True, status="completed", data={"planning": {"plan": _sample_plan().model_dump(mode="json")}}
        ),
    )
    manager._publish_workflow_outputs(run, "e1")
    assert repo.get_plan("e1").phases == []


def test_publish_outreach_stage_advances_vendor_rows(repo: EventRepository):
    manager = RunManager(session_factory=lambda: repo.db)
    repo.save_vendors("e1", _shortlist())
    outreach = OutreachReport(
        event_id="e1",
        candidates=_shortlist().candidates[:2],  # The Grand Pier, Malibu West Beach Club
        send_runs=[
            TaskRun(result=SessionResult(succeeded=True, status="idle", outcome="success", answer="sent")),
            TaskRun(result=SessionResult(succeeded=False, status="failed", error="form rejected")),
        ],
        comparison=QuoteComparison.model_validate(
            {
                "quotes": [
                    {
                        "vendor_name": "The Grand Pier",
                        "category": "venue",
                        "contacted": True,
                        "channel": "form",
                        "quoted_total_usd": 5100,
                    }
                ]
            }
        ),
        succeeded=True,
    )
    stages = {"outreach": outreach.model_dump(mode="json")}
    run = TaskRun(
        agent="workflow/vendor_outreach",
        result=SessionResult(succeeded=True, status="completed", data=stages),
    )

    manager._publish_workflow_outputs(run, "e1")

    vendors = {v.name: v for v in repo.get_vendors("e1")}
    assert (vendors["The Grand Pier"].status, vendors["The Grand Pier"].quotes) == ("Negotiating", 1)
    assert vendors["The Grand Pier"].cost == "$5,100"
    assert vendors["Malibu West Beach Club"].status == "Awaiting you"  # its send failed — untouched


def test_publish_booking_outcome_confirms_the_vendor(repo: EventRepository):
    manager = RunManager(session_factory=lambda: repo.db)
    repo.save_vendors("e1", _shortlist())
    action = {
        "type": "book_vendor",
        "event_id": "e1",
        "candidate": {"name": "Coastal Catering Co", "url": "https://example.com/ccc", "category": "catering"},
        "amount_usd": 2800.0,
    }
    booked = TaskRun(result=SessionResult(succeeded=True, status="idle", outcome="success", answer="booked"))

    manager._publish_booking_outcome(booked, action)

    vendor = next(v for v in repo.get_vendors("e1") if v.name == "Coastal Catering Co")
    assert (vendor.status, vendor.cost) == ("Confirmed", "$2,800")
    assert repo.db.get(orm.Event, "e1").vendors_confirmed == 1

    # A failed booking changes nothing.
    failed = TaskRun(result=SessionResult(succeeded=False, status="failed", error="checkout crashed"))
    manager._publish_booking_outcome(failed, {**action, "candidate": {"name": "The Grand Pier"}})
    assert next(v for v in repo.get_vendors("e1") if v.name == "The Grand Pier").status == "Sourcing"


def test_publish_failure_reports_amber_activity(repo: EventRepository, monkeypatch: pytest.MonkeyPatch):
    manager = RunManager(session_factory=lambda: repo.db)

    def boom(self, *args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(EventRepository, "save_plan", boom)
    stages = {"planning": {"plan": _sample_plan().model_dump(mode="json"), "requirements": None}}
    manager._publish_workflow_outputs(_workflow_run(stages), "e1")  # must not raise

    activity = repo.get_activity("e1")
    assert any(a.tone == "amber" and "couldn't publish" in a.description for a in activity)


# ---- mid-run stage publishing ----


def test_publish_stage_writes_plan_and_vendors_with_feed_lines(repo: EventRepository):
    manager = RunManager(session_factory=lambda: repo.db)
    planning = {
        "plan": _sample_plan().model_dump(mode="json"),
        "requirements": EventRequirements(budget_usd=50_000.0, date="2026-08-06").model_dump(mode="json"),
    }

    assert manager._publish_stage("e1", "planning", planning) is True
    assert repo.get_plan("e1").phases
    assert repo.db.get(orm.Event, "e1").total_usd == 50_000

    assert manager._publish_stage("e1", "sourcing", {"shortlist": _shortlist().model_dump(mode="json")}) is True
    assert len(repo.get_vendors("e1")) == 3

    # An empty shortlist must not clobber the vendors that just landed.
    assert manager._publish_stage("e1", "sourcing", {"shortlist": {"candidates": []}}) is False
    assert len(repo.get_vendors("e1")) == 3

    descriptions = [a.description for a in repo.get_activity("e1")]
    assert any("Plan drafted" in d for d in descriptions)
    assert any("Vendor research complete — 3 candidates" in d for d in descriptions)


def test_publish_skips_already_published_stages(repo: EventRepository):
    manager = RunManager(session_factory=lambda: repo.db)
    repo.save_vendors("e1", _shortlist())
    repo.confirm_vendor("e1", name="Malibu West Beach Club")
    stages = {
        "planning": {"plan": _sample_plan().model_dump(mode="json"), "requirements": None},
        "sourcing": {"shortlist": _shortlist().model_dump(mode="json")},
    }

    manager._publish_workflow_outputs(_workflow_run(stages), "e1", skip_stages={"planning", "sourcing"})

    assert repo.get_plan("e1").phases == []  # planning was already handled mid-run
    booked = next(v for v in repo.get_vendors("e1") if v.name == "Malibu West Beach Club")
    assert booked.status == "Confirmed"  # the tail rewrite would have demoted it back to Awaiting you


# ---- boot-time reconcile of interrupted runs ----


class FakeSessions:
    """Stands in for the SDK's sessions resource during recovery."""

    def __init__(self, summaries: list[SimpleNamespace], sessions: dict[str, SimpleNamespace]) -> None:
        self._summaries = summaries
        self._sessions = sessions
        self.listed: list[dict] = []

    def list_sessions(self, **kwargs) -> SimpleNamespace:
        self.listed.append(kwargs)
        return SimpleNamespace(items=self._summaries)

    def get_session(self, session_id: str) -> SimpleNamespace:
        return self._sessions[session_id]


def _completions(*payloads: dict) -> httpx.Client:
    remaining = list(payloads)

    def respond(request: httpx.Request) -> httpx.Response:
        assert remaining, "recovery made more completion calls than the test scripted"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(remaining.pop(0))}}]})

    return httpx.Client(transport=httpx.MockTransport(respond))


def test_reconcile_recovers_plan_and_vendors_from_h(repo: EventRepository, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    runs_repo = RunRepository(repo.db)
    runs_repo.create(run_id="run-lost", kind="chat", title="Plan this event end-to-end", event_id="e1")
    runs_repo.interrupt_stale()
    memory_repo = MemoryRepository(repo.db)
    memory_repo.set_event_memory(event_id="e1", key=PLAN_SNAPSHOT, value=_sample_plan().model_dump(mode="json"))
    memory_repo.set_event_memory(
        event_id="e1",
        key=REQUIREMENTS,
        value=EventRequirements(budget_usd=50_000.0, date="2026-08-06").model_dump(mode="json"),
    )
    fake_sdk = SimpleNamespace(
        sessions=FakeSessions(
            summaries=[SimpleNamespace(id="s-venue", agent="occasion-venue", status="completed")],
            sessions={
                "s-venue": SimpleNamespace(
                    id="s-venue",
                    status=SimpleNamespace(status="completed", outcome="partial", error=None, error_code=None),
                    latest_answer={
                        "options": [{"name": "Bell Harbor Center", "url": "https://bellharbor.example.com"}],
                        "recommended": "Bell Harbor Center",
                    },
                    agent_view_url="https://h.example/agent/s-venue",
                )
            },
        )
    )
    recovered_shortlist = {
        "candidates": [
            {
                "category": "venue",
                "name": "Bell Harbor Center",
                "url": "https://bellharbor.example.com",
                "price_notes": "$9,000 for 3 days",
                "contact_path": "events@bellharbor.example.com",
                "rank": 1,
            }
        ]
    }
    manager = RunManager(
        session_factory=lambda: repo.db,
        h_client_factory=lambda: HClient(fake_sdk),
        http_client=_completions(recovered_shortlist),
    )

    asyncio.run(manager._reconcile_interrupted())

    assert repo.get_plan("e1").phases  # the plan snapshot reached the dashboard
    assert repo.db.get(orm.Event, "e1").total_usd == 50_000
    (vendor,) = repo.get_vendors("e1")
    assert vendor.name == "Bell Harbor Center"
    settled = runs_repo.get("run-lost")
    assert (settled.status, settled.reason) == ("completed", "recovered after restart")
    assert "the event plan" in settled.result.answer and "1 researched vendors" in settled.result.answer
    assert memory_repo.get_event_memory("e1", SHORTLIST) is not None  # a re-kick skips the fan-out
    descriptions = [a.description for a in repo.get_activity("e1")]
    assert any("Recovered the event plan" in d for d in descriptions)
    assert any("Recovered vendor research" in d for d in descriptions)


def test_reconcile_with_nothing_recoverable_settles_failed(repo: EventRepository):
    runs_repo = RunRepository(repo.db)
    runs_repo.create(run_id="run-lost", kind="chat", title="Plan this event", event_id="e1")
    runs_repo.interrupt_stale()

    def no_h() -> HClient:
        raise AssertionError("without a plan snapshot, H must not be consulted")

    manager = RunManager(session_factory=lambda: repo.db, h_client_factory=no_h)
    asyncio.run(manager._reconcile_interrupted())  # must not raise

    settled = runs_repo.get("run-lost")
    assert (settled.status, settled.reason) == ("failed", "interrupted by a service restart")
    assert any(
        a.tone == "amber" and "nothing could be recovered" in a.description for a in repo.get_activity("e1")
    )


def test_reconcile_skips_recovery_when_a_new_run_is_underway(repo: EventRepository):
    runs_repo = RunRepository(repo.db)
    runs_repo.create(run_id="run-old", kind="chat", title="Plan this event", event_id="e1")
    runs_repo.interrupt_stale()  # strands run-old before the new run starts
    runs_repo.create(run_id="run-new", kind="chat", title="Plan it again", event_id="e1")
    MemoryRepository(repo.db).set_event_memory(
        event_id="e1", key=PLAN_SNAPSHOT, value=_sample_plan().model_dump(mode="json")
    )

    def no_h() -> HClient:
        raise AssertionError("a live run owns the event; H must not be consulted")

    manager = RunManager(session_factory=lambda: repo.db, h_client_factory=no_h)
    asyncio.run(manager._reconcile_interrupted())

    assert (runs_repo.get("run-old").status, runs_repo.get("run-old").reason) == ("failed", "superseded by a newer run")
    assert runs_repo.get("run-new").status == "running"  # untouched
    assert repo.get_plan("e1").phases == []  # no writes under the live run
