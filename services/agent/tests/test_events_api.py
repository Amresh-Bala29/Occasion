"""Tests for the event dashboard API.

The routes are exercised through TestClient with a hand-written fake repository
swapped in via dependency override, so no database is required. The focus is the
JSON contract the web app depends on: camelCase keys and optional fields omitted
(never null) when absent.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from api.dependencies import get_event_repository, get_run_manager, get_supervisor  # noqa: E402
from core.supervisor import (  # noqa: E402
    EventSessionsReport,
    ObstacleLine,
    ObstaclesSummary,
    QuotaSnapshot,
    SessionFrame,
    SessionHealth,
    SessionSnapshot,
)
from database.repositories.run_repository import RunRecord  # noqa: E402
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
        self.created: dict[str, str] | None = None

    def get_dashboard(self, event_id: str) -> web.DashboardData | None:
        return self._dashboard if event_id == EVENT_ID else None

    def list_events(self) -> list[web.EventOverview]:
        return [self._dashboard.event] if self._dashboard else []

    def create_event(self, *, name: str, kind: str, date: str, location: str, headcount: str) -> web.EventOverview:
        self.created = {"name": name, "kind": kind, "date": date, "location": location, "headcount": headcount}
        return web.EventOverview(
            id="test-offsite", kind=kind, name=name, short_name=name, status_label="Planning",
            date=date, location=location, headcount=headcount, days_to_go="TBD", percent_complete=0,
        )

    def update_event(
        self, event_id: str, *, name=None, kind=None, date=None, location=None, headcount=None
    ) -> web.EventOverview | None:
        if self._dashboard is None or event_id != EVENT_ID:
            return None
        self.updated = {"name": name, "kind": kind, "date": date, "location": location, "headcount": headcount}
        base = self._dashboard.event
        return web.EventOverview(
            id=base.id, kind=kind or base.kind, name=name or base.name, short_name=name or base.short_name,
            status_label=base.status_label, date=date or base.date, location=location or base.location,
            headcount=headcount or base.headcount, days_to_go=base.days_to_go, percent_complete=base.percent_complete,
        )

    def list_pending_approvals(self) -> list[web.PendingApproval]:
        return [
            web.PendingApproval(
                id="approval-2", kind="Booking", agent="Entertainment agent", agent_tone="green",
                tag="Deposit", title="DJ", description="d", amount="$3,200", vendor="Marina Sound",
                event_id=EVENT_ID, event_name="NovaFlow Summit 2026",
            )
        ]

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

    # ---- Booking-loop surface (ApprovalManager reads policy through these) ----

    def get_auto_approve_limit(self, event_id: str) -> str | None:
        return "$500"

    def get_spending_rules(self, event_id: str) -> list[web.SpendingRule]:
        return [web.SpendingRule(id="rule-deposits", label="Deposits & payments", value="Auto")]

    def create_approval(self, **kwargs) -> web.ApprovalItem:
        self.created_approval = kwargs
        return web.ApprovalItem(
            id="approval-book-1", kind=kwargs["kind"], agent=kwargs["agent"], agent_tone=kwargs["agent_tone"],
            tag=kwargs["tag"], title=kwargs["title"], description=kwargs["description"],
            amount=kwargs["amount"], vendor=kwargs["vendor"],
        )

    def get_approval_action(self, approval_id: str) -> dict | None:
        return getattr(self, "created_approval", {}).get("action") if approval_id == "approval-book-1" else None


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


def test_list_events_returns_camelcase_summaries() -> None:
    body = _client(FakeRepo(_dashboard())).get("/events").json()

    (event,) = body
    assert event["id"] == EVENT_ID
    assert event["shortName"] == "NovaFlow Summit"
    assert event["percentComplete"] == 68


def test_create_event_returns_created_summary() -> None:
    repo = FakeRepo(_dashboard())
    body = _client(repo).post("/events", json={"name": "Test Offsite"}).json()

    # Body defaults reach the repository; the response is the created summary.
    assert repo.created == {"name": "Test Offsite", "kind": "Event", "date": "TBD", "location": "TBD", "headcount": "TBD"}
    assert body["id"] == "test-offsite"
    assert body["statusLabel"] == "Planning"
    assert body["percentComplete"] == 0


def test_update_event_patches_only_given_fields_and_returns_camelcase() -> None:
    repo = FakeRepo(_dashboard())
    response = _client(repo).patch(f"/events/{EVENT_ID}", json={"location": "Fort Mason, SF"})

    assert response.status_code == 200
    # Only the provided field carries a value; the rest reach the repository as None.
    assert repo.updated == {"name": None, "kind": None, "date": None, "location": "Fort Mason, SF", "headcount": None}
    body = response.json()
    assert body["location"] == "Fort Mason, SF"
    assert body["shortName"] == "NovaFlow Summit"  # untouched fields keep the current row's values


def test_update_missing_event_is_404() -> None:
    response = _client(FakeRepo(None)).patch("/events/does-not-exist", json={"name": "X"})
    assert response.status_code == 404


def test_list_approvals_returns_pending_across_events() -> None:
    body = _client(FakeRepo(_dashboard())).get("/approvals").json()

    (approval,) = body
    assert approval["eventId"] == EVENT_ID
    assert approval["eventName"] == "NovaFlow Summit 2026"
    assert approval["agentTone"] == "green"
    assert "threadId" not in approval  # absent optionals omitted, not null


class FakeRunManager:
    def __init__(self) -> None:
        self.bookings: list[tuple[dict, str]] = []

    def start_booking(self, action: dict, *, approval_note: str) -> RunRecord:
        self.bookings.append((action, approval_note))
        return RunRecord(
            id="run-book1", event_id=action.get("event_id"), kind="booking", title="Book", status="running"
        )


def _booking_client(repo: FakeRepo, manager: FakeRunManager) -> TestClient:
    app.dependency_overrides[get_event_repository] = lambda: repo
    app.dependency_overrides[get_run_manager] = lambda: manager
    return TestClient(app)


def test_booking_under_limit_executes_immediately() -> None:
    manager = FakeRunManager()
    body = _booking_client(FakeRepo(_dashboard()), manager).post(
        f"/events/{EVENT_ID}/bookings",
        json={"vendor_name": "Marina Sound", "url": "https://marinasound.example", "category": "entertainment",
              "amount_usd": 240.0},
    ).json()

    assert body["status"] == "executing"
    assert body["run_id"] == "run-book1"
    ((action, note),) = manager.bookings
    assert action["candidate"]["name"] == "Marina Sound"
    assert action["event_id"] == EVENT_ID
    assert note.startswith("Auto-approved")


def test_booking_over_limit_parks_as_approval_with_action() -> None:
    repo = FakeRepo(_dashboard())
    manager = FakeRunManager()
    body = _booking_client(repo, manager).post(
        f"/events/{EVENT_ID}/bookings",
        json={"vendor_name": "Pier 27", "url": "https://pier27.example", "category": "venue",
              "amount_usd": 12_000.0},
    ).json()

    assert body["status"] == "pending_approval"
    assert body["approval_id"] == "approval-book-1"
    assert manager.bookings == []  # nothing executes until the user approves
    assert repo.created_approval["action"]["candidate"]["url"] == "https://pier27.example"


def test_approving_an_actionable_approval_executes_it() -> None:
    repo = FakeRepo(_dashboard())
    manager = FakeRunManager()
    client = _booking_client(repo, manager)
    client.post(
        f"/events/{EVENT_ID}/bookings",
        json={"vendor_name": "Pier 27", "url": "https://pier27.example", "category": "venue",
              "amount_usd": 12_000.0},
    )

    response = client.post("/approvals/approval-book-1", json={"approved": True})

    assert response.status_code == 200  # decision shape unchanged for the dashboard
    ((action, note),) = manager.bookings
    assert action["candidate"]["name"] == "Pier 27"
    assert "decision-approval-book-1" in note


def test_declining_an_actionable_approval_executes_nothing() -> None:
    repo = FakeRepo(_dashboard())
    manager = FakeRunManager()
    client = _booking_client(repo, manager)
    client.post(
        f"/events/{EVENT_ID}/bookings",
        json={"vendor_name": "Pier 27", "url": "https://pier27.example", "category": "venue",
              "amount_usd": 12_000.0},
    )

    client.post("/approvals/approval-book-1", json={"approved": False})

    assert manager.bookings == []


class FakeSupervisor:
    def __init__(
        self,
        report: EventSessionsReport,
        health: SessionHealth | None = None,
        frame: SessionFrame | None = None,
        obstacle_feed: list[ObstacleLine] | None = None,
    ) -> None:
        self._report = report
        self._health = health
        self._frame = frame
        self._obstacle_feed = list(obstacle_feed or [])

    def event_sessions(self, event_id: str) -> EventSessionsReport:
        return self._report

    def session_health(self, session_id: str) -> SessionHealth:
        assert self._health is not None, "test asked for health without providing one"
        return self._health

    def session_frame(self, session_id: str) -> SessionFrame:
        assert self._frame is not None, "test asked for a frame without providing one"
        return self._frame

    def drain_obstacle_feed(self, session_id: str) -> list[ObstacleLine]:
        pending, self._obstacle_feed = self._obstacle_feed, []
        return pending


class FakeActivityRepo:
    """Records the frame route's activity writes; raises on demand."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.activity: list[dict] = []

    def add_activity(self, event_id: str, *, agent: str, tone: str, description: str) -> None:
        if self._error is not None:
            raise self._error
        self.activity.append({"event_id": event_id, "agent": agent, "tone": tone, "description": description})


def _supervisor_client(
    report: EventSessionsReport,
    health: SessionHealth | None = None,
    frame: SessionFrame | None = None,
    obstacle_feed: list[ObstacleLine] | None = None,
    activity_repo: FakeActivityRepo | None = None,
) -> TestClient:
    # One shared fake per client: drain-once semantics must hold across requests.
    fake = FakeSupervisor(report, health, frame, obstacle_feed)
    repo = activity_repo or FakeActivityRepo()
    app.dependency_overrides[get_supervisor] = lambda: fake
    app.dependency_overrides[get_event_repository] = lambda: repo
    return TestClient(app)


def test_agent_sessions_returns_live_report() -> None:
    report = EventSessionsReport(
        succeeded=True,
        event_id=EVENT_ID,
        sessions=[
            SessionSnapshot(
                id="sess_1",
                agent="occasion-venue",
                status="running",
                task="Research three venues",
                agent_view_url="https://platform.hcompany.ai/agents/sessions/sess_1",
                created_at=datetime(2026, 7, 11, 20, 0, tzinfo=timezone.utc),
            )
        ],
        quota=QuotaSnapshot(limit=3, active=1, available=2),
    )
    body = _supervisor_client(report).get(f"/events/{EVENT_ID}/agent-sessions").json()

    # snake_case keys: this is the live-surface contract, like SessionResult — not a
    # models/web.py mirror of the TS mocks.
    assert body["succeeded"] is True
    assert body["event_id"] == EVENT_ID
    (session,) = body["sessions"]
    assert session["id"] == "sess_1"
    assert session["agent"] == "occasion-venue"
    assert session["status"] == "running"
    assert session["task"] == "Research three venues"
    assert session["agent_view_url"].endswith("sess_1")
    assert "finished_at" not in session  # absent optionals omitted, not null
    assert body["quota"] == {"limit": 3, "active": 1, "available": 2}
    assert "error" not in body


def test_agent_sessions_failure_is_200_with_honest_error() -> None:
    report = EventSessionsReport(succeeded=False, event_id=EVENT_ID, error="quota check failed: HTTP 503: down")
    response = _supervisor_client(report).get(f"/events/{EVENT_ID}/agent-sessions")

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is False
    assert "503" in body["error"]
    assert body["sessions"] == []


def test_session_health_returns_live_snapshot() -> None:
    health = SessionHealth(succeeded=True, session_id="sess_1", status="running", steps=12)
    client = _supervisor_client(EventSessionsReport(succeeded=True, event_id=EVENT_ID), health)
    body = client.get(f"/events/{EVENT_ID}/sessions/sess_1/health").json()

    assert body["succeeded"] is True
    assert body["session_id"] == "sess_1"  # snake_case, like every live surface
    assert body["status"] == "running"
    assert body["steps"] == 12
    assert "error" not in body  # absent optionals omitted, not null
    assert "outcome" not in body


def test_session_health_failure_is_200_with_honest_error() -> None:
    health = SessionHealth(succeeded=False, session_id="sess_x", status="error", error="HTTP 503: down")
    client = _supervisor_client(EventSessionsReport(succeeded=True, event_id=EVENT_ID), health)
    response = client.get(f"/events/{EVENT_ID}/sessions/sess_x/health")

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is False
    assert body["status"] == "error"
    assert "503" in body["error"]


def test_session_frame_returns_latest_screenshot() -> None:
    frame = SessionFrame(
        succeeded=True,
        session_id="sess_1",
        at=datetime(2026, 7, 11, 20, 0, tzinfo=timezone.utc),
        page_title="Google",
        media_type="image/png",
        image_base64="aGVsbG8=",
    )
    client = _supervisor_client(EventSessionsReport(succeeded=True, event_id=EVENT_ID), frame=frame)
    body = client.get(f"/events/{EVENT_ID}/sessions/sess_1/frame").json()

    assert body["succeeded"] is True
    assert body["session_id"] == "sess_1"  # snake_case, like every live surface
    assert body["image_base64"] == "aGVsbG8="
    assert body["page_title"] == "Google"
    assert body["at"] == "2026-07-11T20:00:00Z"
    assert "error" not in body  # absent optionals omitted, not null
    assert "page_url" not in body


def test_session_frame_failure_is_200_with_honest_error() -> None:
    frame = SessionFrame(succeeded=False, session_id="sess_x", error="frame fetch failed: HTTP 503: down")
    client = _supervisor_client(EventSessionsReport(succeeded=True, event_id=EVENT_ID), frame=frame)
    response = client.get(f"/events/{EVENT_ID}/sessions/sess_x/frame")

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is False
    assert "503" in body["error"]
    assert "image_base64" not in body


def test_session_frame_serializes_obstacle_fields() -> None:
    frame = SessionFrame(
        succeeded=True,
        session_id="sess_1",
        handling="cookie wall",
        obstacles_cleared=["closed popup on lu.ma"],
    )
    client = _supervisor_client(EventSessionsReport(succeeded=True, event_id=EVENT_ID), frame=frame)
    body = client.get(f"/events/{EVENT_ID}/sessions/sess_1/frame").json()

    assert body["handling"] == "cookie wall"  # snake_case, like every live surface
    assert body["obstacles_cleared"] == ["closed popup on lu.ma"]

    bare = SessionFrame(succeeded=True, session_id="sess_1")
    client = _supervisor_client(EventSessionsReport(succeeded=True, event_id=EVENT_ID), frame=bare)
    body = client.get(f"/events/{EVENT_ID}/sessions/sess_1/frame").json()
    assert "handling" not in body  # absent optionals omitted, not null


def test_session_frame_writes_cleared_obstacles_to_activity() -> None:
    feed = [
        ObstacleLine(session_id="sess_1", agent="occasion-venue", kind="cookie", label="dismissed cookie wall on eventbrite.com"),
        ObstacleLine(session_id="sess_1", agent=None, kind="popup", label="closed popup"),
    ]
    repo = FakeActivityRepo()
    frame = SessionFrame(succeeded=True, session_id="sess_1")
    client = _supervisor_client(
        EventSessionsReport(succeeded=True, event_id=EVENT_ID),
        frame=frame,
        obstacle_feed=feed,
        activity_repo=repo,
    )
    body = client.get(f"/events/{EVENT_ID}/sessions/sess_1/frame").json()

    assert body["succeeded"] is True
    first, second = repo.activity
    assert first["event_id"] == EVENT_ID
    assert first["agent"] == "Venue agent"  # "occasion-venue" humanized for the feed
    assert first["tone"] == "green"
    assert first["description"] == "✓ Dismissed cookie wall on eventbrite.com — kept going."
    assert second["agent"] == "Web agent"  # nameless sessions still get a byline

    # Drain-once: the next poll finds nothing new to write.
    client.get(f"/events/{EVENT_ID}/sessions/sess_1/frame")
    assert len(repo.activity) == 2


def test_session_frame_activity_write_failure_never_breaks_frame() -> None:
    feed = [ObstacleLine(session_id="sess_1", kind="popup", label="closed popup")]
    repo = FakeActivityRepo(error=RuntimeError("db down"))
    frame = SessionFrame(succeeded=True, session_id="sess_1", media_type="image/png", image_base64="aGVsbG8=")
    client = _supervisor_client(
        EventSessionsReport(succeeded=True, event_id=EVENT_ID),
        frame=frame,
        obstacle_feed=feed,
        activity_repo=repo,
    )
    response = client.get(f"/events/{EVENT_ID}/sessions/sess_1/frame")

    assert response.status_code == 200  # the tile keeps its frame no matter what
    assert response.json()["image_base64"] == "aGVsbG8="


def test_agent_sessions_serializes_obstacles_summary() -> None:
    report = EventSessionsReport(
        succeeded=True,
        event_id=EVENT_ID,
        obstacles=ObstaclesSummary(
            cleared_total=3,
            lines=[ObstacleLine(session_id="sess_1", agent="occasion-venue", kind="cookie", label="dismissed cookie wall")],
        ),
    )
    body = _supervisor_client(report).get(f"/events/{EVENT_ID}/agent-sessions").json()

    assert body["obstacles"]["cleared_total"] == 3
    (line,) = body["obstacles"]["lines"]
    assert line["label"] == "dismissed cookie wall"
    assert line["kind"] == "cookie"

    bare = _supervisor_client(EventSessionsReport(succeeded=True, event_id=EVENT_ID)).get(
        f"/events/{EVENT_ID}/agent-sessions"
    )
    assert "obstacles" not in bare.json()  # absent until anything was cleared
