"""Tests for the planning modules and the plan-persistence round-trip.

The transform classes are pure — they take the pipeline's EventPlan (plus an optional
BudgetReview / requirements and a fixed clock) and return detached ORM rows — so they're
asserted directly, no database. One round-trip test exercises save_plan against an
in-memory SQLite built over just the plan tables, checking the group→task flush and the
DTO read path without touching the real Postgres.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy import event as sa_event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

# Make the agent service root importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@compiles(BigInteger, "sqlite")
def _sqlite_bigint_as_integer(_type, _compiler, **_kw):
    # SQLite only autoincrements an INTEGER PRIMARY KEY, not BIGINT; the identity PKs
    # (plan_phases, risks, …) rely on it. Postgres keeps its bigint identity untouched.
    return "INTEGER"

from agents.budget_agent import BudgetLine, BudgetReview  # noqa: E402
from agents.requirements_agent import EventRequirements  # noqa: E402
from database import models as orm  # noqa: E402
from database.repositories.event_repository import EventRepository  # noqa: E402
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

    event = repo.db.get(orm.Event, "e1")
    assert event.percent_complete == 17
    assert event.total_usd == 50_000
    assert event.paid_usd == 12_000
    assert event.pending_usd == 12_000  # committed 24,000 − paid 12,000


def test_save_plan_is_idempotent(repo: EventRepository):
    repo.save_plan("e1", _sample_plan(), today=TODAY)
    repo.save_plan("e1", _sample_plan(), today=TODAY)
    plan = repo.get_plan("e1")
    assert sum(len(g.tasks) for g in plan.groups) == 5  # five checklist items, not doubled
