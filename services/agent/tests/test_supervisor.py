"""Tests for the supervisor: session listings, health checks, quota, and cancel.

The hai-agents SDK is never called for real — a fake sessions API stands in, so the
tests assert how H's session vocabulary is normalized into the supervisor's reports.
"""

from __future__ import annotations

import base64
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx

# Make the agent service root importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings  # noqa: E402
from core.supervisor import (  # noqa: E402
    _ACTIVE_STATUSES,
    _FRAME_EVENT_PAGE_SIZE,
    _RECENT_TERMINAL_LIMIT,
    _TERMINAL_STATUSES,
    _frame_cache,
    _obstacle_ledger,
    Supervisor,
)

CREATED = datetime(2026, 7, 11, 20, 0, tzinfo=timezone.utc)


def minute(n: int) -> datetime:
    """A timestamp n minutes into the session — detection orders events by time."""
    return CREATED + timedelta(minutes=n)


def summary(**fields) -> SimpleNamespace:
    """A SessionSummary look-alike; unset fields default to None."""
    defaults = {
        "id": "sess_1",
        "agent": "h/web-surfer-flash",
        "status": "running",
        "agent_view_url": None,
        "first_message": None,
        "created_at": CREATED,
        "started_at": None,
        "finished_at": None,
    }
    return SimpleNamespace(**{**defaults, **fields})


def session_status(**fields) -> SimpleNamespace:
    """A SessionStatus look-alike; unset fields default to None/empty."""
    defaults = {
        "status": "running",
        "error": None,
        "error_code": None,
        "outcome": None,
        "steps": None,
        "subagent_session_ids": [],
    }
    return SimpleNamespace(**{**defaults, **fields})


def agent_event(kind: str, at: datetime | None = None, **fields) -> SimpleNamespace:
    """An AgentEvent look-alike from the session's trajectory stream."""
    return SimpleNamespace(type="AgentEvent", timestamp=at or CREATED, data=SimpleNamespace(kind=kind, **fields))


def observation(
    image: SimpleNamespace | None, metadata: dict | None = None, at: datetime | None = None
) -> SimpleNamespace:
    return agent_event("observation_event", at=at, type="web", text=None, image=image, metadata=metadata or {})


def policy(text: str, at: datetime | None = None) -> SimpleNamespace:
    """A policy_event look-alike: the agent narrating its next move."""
    return agent_event("policy_event", at=at, content=text, reasoning_content=None, tool_reqs=[])


def scroll_result(at: datetime | None = None) -> SimpleNamespace:
    """A tool_result look-alike for one executed scroll action."""
    return agent_event(
        "tool_result", at=at, tool_req=SimpleNamespace(tool_name="scroll_down", args={}), result="ok"
    )


def error_event(message: str, at: datetime | None = None) -> SimpleNamespace:
    return agent_event("error_event", at=at, error=message, origin="env", tool_req=None)


def image(type: str, source: str, media_type: str = "image/png") -> SimpleNamespace:
    """An ImageContent look-alike; `type` and `source` mirror the wire fields."""
    return SimpleNamespace(type=type, source=source, media_type=media_type)


class FakeSessionsAPI:
    """Stands in for client.sessions: records calls, returns or raises presets."""

    def __init__(
        self,
        page_items: list | None = None,
        list_error: Exception | None = None,
        quota: SimpleNamespace | None = None,
        quota_error: Exception | None = None,
        status: SimpleNamespace | None = None,
        status_error: Exception | None = None,
        cancel_error: Exception | None = None,
        events_page: list | None = None,
        events_error: Exception | None = None,
    ) -> None:
        self._page_items = page_items or []
        self._list_error = list_error
        self._quota = quota or SimpleNamespace(limit=3, active=1, available=2)
        self._quota_error = quota_error
        self._status = status
        self._status_error = status_error
        self._cancel_error = cancel_error
        self._events_page = events_page or []
        self._events_error = events_error
        self.list_calls: list[dict] = []
        self.status_calls: list[str] = []
        self.cancel_calls: list[str] = []
        self.events_calls: list[tuple[str, dict]] = []

    def list_sessions(self, **kwargs) -> SimpleNamespace:
        self.list_calls.append(kwargs)
        if self._list_error is not None:
            raise self._list_error
        return SimpleNamespace(items=self._page_items)

    def get_session_quota(self) -> SimpleNamespace:
        if self._quota_error is not None:
            raise self._quota_error
        return self._quota

    def get_session_status(self, session_id: str) -> SimpleNamespace:
        self.status_calls.append(session_id)
        if self._status_error is not None:
            raise self._status_error
        return self._status

    def cancel_session(self, session_id: str) -> None:
        self.cancel_calls.append(session_id)
        if self._cancel_error is not None:
            raise self._cancel_error

    def list_session_events(self, session_id: str, **kwargs) -> SimpleNamespace:
        self.events_calls.append((session_id, kwargs))
        if self._events_error is not None:
            raise self._events_error
        return SimpleNamespace(items=self._events_page)


def supervisor_with(api: FakeSessionsAPI, http_client: httpx.Client | None = None) -> Supervisor:
    return Supervisor(SimpleNamespace(sessions=api), http_client=http_client)


def test_event_sessions_lists_active_runs(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    api = FakeSessionsAPI(
        page_items=[
            summary(
                id="sess_1",
                status="running",
                first_message=SimpleNamespace(message="Research three venues"),
                agent_view_url="https://platform.hcompany.ai/agents/sessions/sess_1",
            ),
            summary(id="sess_2", agent="occasion-venue", status="idle"),
        ],
    )
    report = supervisor_with(api).event_sessions("evt-9")

    assert report.succeeded is True
    assert report.event_id == "evt-9"
    assert report.error is None
    (call,) = api.list_calls
    assert call["group_id"] == "evt-9"  # the orchestrator tags every session with the event id
    # Active states hold slots; terminal ones ride along so finished replays stay reachable.
    assert call["status"] == list(_ACTIVE_STATUSES) + list(_TERMINAL_STATUSES)
    first, second = report.sessions
    assert first.id == "sess_1"
    assert first.task == "Research three venues"
    assert first.agent_view_url.endswith("sess_1")
    assert first.created_at == CREATED
    assert second.agent == "occasion-venue"
    assert second.status == "idle"
    assert report.quota.limit == 3
    assert report.quota.active == 1
    assert report.quota.available == 2


def test_event_sessions_caps_finished_history(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    finished = [
        summary(id=f"done_{n}", status="completed", finished_at=CREATED)
        for n in range(_RECENT_TERMINAL_LIMIT + 2)
    ]
    # Newest-first like H returns: one live session, then a long finished history.
    api = FakeSessionsAPI(page_items=[summary(id="live_1", status="running"), *finished])
    report = supervisor_with(api).event_sessions("evt-9")

    assert [s.id for s in report.sessions][:1] == ["live_1"]  # active always kept, order preserved
    assert sum(s.status == "completed" for s in report.sessions) == _RECENT_TERMINAL_LIMIT
    assert len(report.sessions) == 1 + _RECENT_TERMINAL_LIMIT


def test_event_sessions_quota_failure_keeps_sessions(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    boom = RuntimeError("quota service down")
    boom.status_code = 503  # mimic hai_agents.core.ApiError carrying an HTTP status
    api = FakeSessionsAPI(page_items=[summary()], quota_error=boom)
    report = supervisor_with(api).event_sessions("evt-9")

    assert report.succeeded is False  # the report as a whole is not trustworthy
    assert len(report.sessions) == 1  # but nothing fetched is thrown away
    assert report.quota is None
    assert "quota check failed" in report.error
    assert "503" in report.error


def test_event_sessions_listing_failure_is_honest(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    api = FakeSessionsAPI(list_error=RuntimeError("listing down"))
    report = supervisor_with(api).event_sessions("evt-9")

    assert report.succeeded is False
    assert report.sessions == []
    assert "session listing failed" in report.error
    assert report.quota is not None  # the quota call still answered


def test_event_sessions_requires_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "")
    api = FakeSessionsAPI(list_error=AssertionError("SDK must not be called without a key"))
    report = supervisor_with(api).event_sessions("evt-9")

    assert report.succeeded is False
    assert "HAI_API_KEY" in report.error
    assert api.list_calls == []


def test_session_health_maps_live_status(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    api = FakeSessionsAPI(status=session_status(status="running", steps=14, subagent_session_ids=["child_1"]))
    health = supervisor_with(api).session_health("sess_1")

    assert health.succeeded is True
    assert health.status == "running"
    assert health.steps == 14
    assert health.subagent_session_ids == ["child_1"]
    assert api.status_calls == ["sess_1"]


def test_session_health_failed_terminal_state(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    api = FakeSessionsAPI(status=session_status(status="timed_out", error_code="timeout"))
    health = supervisor_with(api).session_health("sess_1")

    assert health.succeeded is False
    assert health.status == "timed_out"
    assert health.error == "timeout"


def test_session_health_check_failure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    api = FakeSessionsAPI(status_error=RuntimeError("no such session"))
    health = supervisor_with(api).session_health("sess_x")

    assert health.succeeded is False
    assert health.status == "error"  # the check itself failed; no lifecycle state known
    assert "no such session" in health.error


def test_cancel_session(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    api = FakeSessionsAPI()
    result = supervisor_with(api).cancel_session("sess_1")

    assert result.succeeded is True
    assert result.error is None
    assert api.cancel_calls == ["sess_1"]


def test_cancel_session_failure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    api = FakeSessionsAPI(cancel_error=RuntimeError("already terminal"))
    result = supervisor_with(api).cancel_session("sess_1")

    assert result.succeeded is False
    assert "already terminal" in result.error


PNG_BYTES = b"\x89PNG fake screenshot bytes"


def test_session_frame_inlines_base64_image(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    _frame_cache.clear()
    api = FakeSessionsAPI(
        events_page=[
            agent_event("policy_event", content="click the first result"),
            observation(image("base64", "aGVsbG8="), metadata={"title": "Google", "url": "https://google.com"}),
        ]
    )
    frame = supervisor_with(api).session_frame("sess_1")

    assert frame.succeeded is True
    assert frame.image_base64 == "aGVsbG8="  # a base64 source *is* the payload
    assert frame.media_type == "image/png"
    assert frame.page_title == "Google"
    assert frame.page_url == "https://google.com"
    assert frame.at == CREATED
    ((session_id, kwargs),) = api.events_calls
    assert session_id == "sess_1"
    assert kwargs == {"size": _FRAME_EVENT_PAGE_SIZE, "sort": ["-timestamp"], "type": "AgentEvent"}


def test_session_frame_fetches_url_image_with_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    _frame_cache.clear()

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer hk-test"
        return httpx.Response(200, content=PNG_BYTES)

    api = FakeSessionsAPI(events_page=[observation(image("url", "https://agp.test/shot.png"))])
    http = httpx.Client(transport=httpx.MockTransport(respond))
    frame = supervisor_with(api, http_client=http).session_frame("sess_1")

    assert frame.succeeded is True
    assert frame.image_base64 == base64.b64encode(PNG_BYTES).decode("ascii")


def test_session_frame_follows_redirect_without_leaking_the_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    _frame_cache.clear()
    hops: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        hops.append(request)
        if request.url.host == "agp.test":
            return httpx.Response(302, headers={"location": "https://s3.test/shot.png?sig=abc"})
        # S3 rejects presigned requests that also carry an Authorization header.
        assert "authorization" not in request.headers
        return httpx.Response(200, content=PNG_BYTES)

    api = FakeSessionsAPI(events_page=[observation(image("url", "https://agp.test/shot.png"))])
    http = httpx.Client(transport=httpx.MockTransport(respond))
    frame = supervisor_with(api, http_client=http).session_frame("sess_1")

    assert frame.succeeded is True
    assert [request.url.host for request in hops] == ["agp.test", "s3.test"]


def test_session_frame_reports_screenshot_fetch_failure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    _frame_cache.clear()
    api = FakeSessionsAPI(events_page=[observation(image("url", "https://agp.test/gone.png"))])
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))
    frame = supervisor_with(api, http_client=http).session_frame("sess_1")

    assert frame.succeeded is False
    assert "screenshot fetch failed" in frame.error
    assert frame.image_base64 is None


def test_session_frame_before_first_observation_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    _frame_cache.clear()
    api = FakeSessionsAPI(events_page=[agent_event("policy_event", content="planning")])
    frame = supervisor_with(api).session_frame("sess_1")

    # Queued/pending sessions have no screenshot yet; that is not a failure.
    assert frame.succeeded is True
    assert frame.image_base64 is None
    assert frame.error is None


def test_session_frame_skips_imageless_observations(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    _frame_cache.clear()
    api = FakeSessionsAPI(
        events_page=[
            observation(image=None),  # newest observation arrived without a screenshot
            observation(image("base64", "b2xk")),
        ]
    )
    frame = supervisor_with(api).session_frame("sess_1")

    assert frame.image_base64 == "b2xk"


def test_session_frame_listing_failure_is_honest(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    _frame_cache.clear()
    api = FakeSessionsAPI(events_error=RuntimeError("events down"))
    frame = supervisor_with(api).session_frame("sess_1")

    assert frame.succeeded is False
    assert "frame fetch failed" in frame.error


def test_session_frame_requires_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "")
    _frame_cache.clear()
    api = FakeSessionsAPI(events_error=AssertionError("SDK must not be called without a key"))
    frame = supervisor_with(api).session_frame("sess_1")

    assert frame.succeeded is False
    assert "HAI_API_KEY" in frame.error
    assert api.events_calls == []


def test_session_frame_short_cache_dedupes_polls(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    _frame_cache.clear()
    api = FakeSessionsAPI(events_page=[observation(image("base64", "aGk="))])
    supervisor = supervisor_with(api)

    first = supervisor.session_frame("sess_1")
    second = supervisor.session_frame("sess_1")
    assert len(api.events_calls) == 1  # the second poll rode the cache
    assert second == first

    monkeypatch.setattr("core.supervisor._FRAME_TTL_S", 0.0)
    supervisor.session_frame("sess_1")
    assert len(api.events_calls) == 2  # expired entries are refetched


# --- Obstacle detection: the messy web the sessions work through ---


def _fresh_detection(monkeypatch) -> None:
    """Every detection test starts with an empty frame cache and obstacle ledger."""
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    _frame_cache.clear()
    _obstacle_ledger.clear()


def test_frame_detects_cookie_handling(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    # The newest event is mid-obstacle: handled, not yet cleared.
    api = FakeSessionsAPI(events_page=[policy("dismiss the cookie consent banner — click Reject all", at=minute(1))])
    supervisor = supervisor_with(api)
    frame = supervisor.session_frame("sess_1")

    assert frame.handling == "cookie wall"
    assert frame.obstacles_cleared == []
    assert supervisor.drain_obstacle_feed("sess_1") == []  # nothing cleared yet


def test_frame_reports_cleared_cookie_and_queues_feed_line(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    # Newest-first, like H returns: the agent moved on, so the wall is behind it.
    api = FakeSessionsAPI(
        events_page=[
            policy("open the first venue result", at=minute(2)),
            policy("accept all on the cookie consent banner", at=minute(1)),
        ]
    )
    supervisor = supervisor_with(api)
    frame = supervisor.session_frame("sess_1")

    assert frame.handling is None
    assert frame.obstacles_cleared == ["dismissed cookie wall"]
    (line,) = supervisor.drain_obstacle_feed("sess_1")
    assert line.kind == "cookie"
    assert line.session_id == "sess_1"
    assert supervisor.drain_obstacle_feed("sess_1") == []  # drain-once


def test_frame_cleared_label_carries_page_host(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    api = FakeSessionsAPI(
        events_page=[
            observation(image=None, metadata={"url": "https://www.eventbrite.com/d/venues/"}, at=minute(3)),
            policy("open the first venue result", at=minute(2)),
            policy("accept all on the cookie consent banner", at=minute(1)),
        ]
    )
    frame = supervisor_with(api).session_frame("sess_1")

    assert frame.obstacles_cleared == ["dismissed cookie wall on eventbrite.com"]


def test_frame_scroll_drain_uses_agent_stated_count(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    api = FakeSessionsAPI(
        events_page=[
            policy("compare the venues", at=minute(2)),
            policy("scrolled to load more; 24 results are now visible", at=minute(1)),
        ]
    )
    frame = supervisor_with(api).session_frame("sess_1")

    assert frame.obstacles_cleared == ["scrolled 24 results"]


def test_frame_scroll_drain_without_count_stays_honest(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    # No result count anywhere: the label claims the actions taken, never invents results.
    api = FakeSessionsAPI(
        events_page=[
            policy("open the third listing", at=minute(5)),
            scroll_result(at=minute(4)),
            scroll_result(at=minute(3)),
            scroll_result(at=minute(2)),
        ]
    )
    frame = supervisor_with(api).session_frame("sess_1")

    assert frame.obstacles_cleared == ["scrolled ×3 to load more"]


def test_frame_single_scroll_is_navigation_not_obstacle(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    api = FakeSessionsAPI(
        events_page=[
            policy("open the third listing", at=minute(2)),
            scroll_result(at=minute(1)),
        ]
    )
    frame = supervisor_with(api).session_frame("sess_1")

    assert frame.obstacles_cleared == []  # one scroll is just moving around a page


def test_frame_recovery_after_error(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    api = FakeSessionsAPI(
        events_page=[
            policy("reload the page and continue", at=minute(2)),
            error_event("net::ERR_CONNECTION_RESET", at=minute(1)),
        ]
    )
    frame = supervisor_with(api).session_frame("sess_1")

    assert frame.handling is None
    assert frame.obstacles_cleared == ["recovered after error"]


def test_frame_recovering_while_error_is_newest(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    api = FakeSessionsAPI(events_page=[error_event("tab crashed", at=minute(1))])
    frame = supervisor_with(api).session_frame("sess_1")

    assert frame.handling == "recovering"
    assert frame.obstacles_cleared == []


def test_frame_blocker_is_handling_not_cleared(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    monkeypatch.setattr("core.supervisor._FRAME_TTL_S", 0.0)
    api = FakeSessionsAPI(
        events_page=[policy("blocked by a CAPTCHA on the sign-in page, stopping to report", at=minute(1))]
    )
    supervisor = supervisor_with(api)
    frame = supervisor.session_frame("sess_1")
    assert frame.handling == "blocked: CAPTCHA"
    assert frame.obstacles_cleared == []

    # Even once the agent moves on (to wrap up and report), a blocker never earns a ✓.
    api._events_page = [
        policy("summarize findings so far for the final answer", at=minute(2)),
        *api._events_page,
    ]
    frame = supervisor.session_frame("sess_1")
    assert frame.handling is None
    assert frame.obstacles_cleared == []
    assert supervisor.drain_obstacle_feed("sess_1") == []


def test_obstacle_feed_dedupes_per_kind_per_session(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    monkeypatch.setattr("core.supervisor._FRAME_TTL_S", 0.0)
    api = FakeSessionsAPI(
        events_page=[
            policy("open the first venue result", at=minute(2)),
            policy("dismiss the cookie consent banner", at=minute(1)),
        ]
    )
    supervisor = supervisor_with(api)
    first = supervisor.session_frame("sess_1")
    assert first.obstacles_cleared == ["dismissed cookie wall"]

    # A second wall on a later page: shown on the tile, but no second feed line.
    api._events_page = [
        policy("compare pricing across the shortlist", at=minute(12)),
        policy("accept all on the cookie consent overlay", at=minute(11)),
    ]
    second = supervisor.session_frame("sess_1")
    assert len(second.obstacles_cleared) == 2
    drained = supervisor.drain_obstacle_feed("sess_1")
    assert [line.kind for line in drained] == ["cookie"]  # one line per kind per session


def test_event_sessions_reports_obstacle_summary(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    api = FakeSessionsAPI(
        page_items=[summary(id="sess_1", agent="occasion-venue")],
        events_page=[
            policy("open the first venue result", at=minute(2)),
            policy("dismiss the cookie consent banner", at=minute(1)),
        ],
    )
    supervisor = supervisor_with(api)
    supervisor.session_frame("sess_1")  # seeds the ledger with one cleared wall
    report = supervisor.event_sessions("evt-9")

    assert report.obstacles is not None
    assert report.obstacles.cleared_total == 1
    (line,) = report.obstacles.lines
    assert line.kind == "cookie"
    assert line.agent == "occasion-venue"  # the listing stamps the name onto ledger lines


def test_event_sessions_without_obstacles_omits_summary(monkeypatch) -> None:
    _fresh_detection(monkeypatch)
    api = FakeSessionsAPI(page_items=[summary()])
    report = supervisor_with(api).event_sessions("evt-9")

    assert report.obstacles is None
