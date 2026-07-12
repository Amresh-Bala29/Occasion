"""Tests for the event dashboard API.

The routes are exercised through TestClient with a hand-written fake repository
swapped in via dependency override, so no database is required. The focus is the
JSON contract the web app depends on: camelCase keys and optional fields omitted
(never null) when absent.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from api.dependencies import get_event_repository  # noqa: E402
from main import app  # noqa: E402
from models import web  # noqa: E402

EVENT_ID = "novaflow-summit-2026"


def _dashboard() -> web.DashboardData:
    return web.DashboardData(
        event=web.EventOverview(
            id=EVENT_ID,
            kind="Company summit",
            name="NovaFlow Summit 2026",
            short_name="NovaFlow Summit",
            status_label="On track",
            date="Aug 6, 2026",
            location="Pier 27, SF",
            headcount="320 guests",
            days_to_go="26 days",
            percent_complete=68,
        ),
        budget=web.BudgetOverview(total_usd=85_000, paid_usd=22_100, pending_usd=36_300),
        vendors=web.VendorOverview(confirmed=7, total=11, in_progress=4),
        approvals=[
            web.ApprovalItem(
                id="approval-1", kind="Purchase", agent="Purchasing agent", agent_tone="amber",
                tag="Over limit", title="Totes", description="d", amount="$2,940",
                vendor="4imprint", thread_id="thread-4imprint",
            ),
            web.ApprovalItem(
                id="approval-2", kind="Booking", agent="Entertainment agent", agent_tone="green",
                tag="Deposit", title="DJ", description="d", amount="$3,200", vendor="Marina Sound",
            ),
        ],
        agents=[web.AgentStatus(name="Venue", tone="green", status="Booked")],
        activity=[web.ActivityItem(id="a1", agent="Marketing", tone="blue", time_ago="35s ago", description="d")],
        agents_working=8,
        messages_count=4,
        auto_approve_limit="$500",
    )


class FakeRepo:
    def __init__(self, dashboard: web.DashboardData | None) -> None:
        self._dashboard = dashboard

    def get_dashboard(self, event_id: str) -> web.DashboardData | None:
        return self._dashboard if event_id == EVENT_ID else None

    def get_budget(self, event_id: str) -> web.BudgetDetail:
        return web.BudgetDetail(
            categories=[
                web.BudgetCategory(name="Venue", committed_usd=24_000, paid_usd=12_000),
                web.BudgetCategory(name="Decorations", committed_usd=4_000, paid_usd=0, estimate=True),
            ],
            savings=[],
            savings_footnote="footnote",
        )

    def resolve_approval(self, approval_id: str, approved: bool) -> web.DecisionRecord | None:
        if approval_id == "missing":
            return None
        return web.DecisionRecord(
            id=f"decision-{approval_id}", title="Totes", amount="$2,940", when="just now", approved=approved
        )


def _client(repo: FakeRepo) -> TestClient:
    app.dependency_overrides[get_event_repository] = lambda: repo
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_dashboard_returns_camelcase_and_omits_absent_optionals() -> None:
    body = _client(FakeRepo(_dashboard())).get(f"/events/{EVENT_ID}/dashboard").json()

    assert body["autoApproveLimit"] == "$500"
    assert body["agentsWorking"] == 8
    assert body["messagesCount"] == 4
    assert body["vendors"] == {"confirmed": 7, "total": 11, "inProgress": 4}
    assert body["budget"]["totalUsd"] == 85_000

    first, second = body["approvals"]
    assert first["agentTone"] == "amber"
    assert first["threadId"] == "thread-4imprint"
    # Absent optional is omitted, not null — matches the mock.
    assert "threadId" not in second


def test_dashboard_missing_event_is_404() -> None:
    response = _client(FakeRepo(None)).get("/events/does-not-exist/dashboard")
    assert response.status_code == 404


def test_budget_omits_estimate_when_absent() -> None:
    body = _client(FakeRepo(_dashboard())).get(f"/events/{EVENT_ID}/budget").json()

    venue, decorations = body["categories"]
    assert venue["committedUsd"] == 24_000
    assert "estimate" not in venue
    assert decorations["estimate"] is True


def test_resolve_approval_returns_decision() -> None:
    response = _client(FakeRepo(_dashboard())).post("/approvals/approval-1", json={"approved": True})

    assert response.status_code == 200
    assert response.json() == {
        "id": "decision-approval-1",
        "title": "Totes",
        "amount": "$2,940",
        "when": "just now",
        "approved": True,
    }


def test_resolve_missing_approval_is_404() -> None:
    response = _client(FakeRepo(_dashboard())).post("/approvals/missing", json={"approved": False})
    assert response.status_code == 404
