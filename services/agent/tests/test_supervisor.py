"""Tests for the supervisor: session listings, health checks, quota, and cancel.

The hai-agents SDK is never called for real — a fake sessions API stands in, so the
tests assert how H's session vocabulary is normalized into the supervisor's reports.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

# Make the agent service root importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings  # noqa: E402
from core.supervisor import _ACTIVE_STATUSES, Supervisor  # noqa: E402

CREATED = datetime(2026, 7, 11, 20, 0, tzinfo=timezone.utc)


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
    ) -> None:
        self._page_items = page_items or []
        self._list_error = list_error
        self._quota = quota or SimpleNamespace(limit=3, active=1, available=2)
        self._quota_error = quota_error
        self._status = status
        self._status_error = status_error
        self._cancel_error = cancel_error
        self.list_calls: list[dict] = []
        self.status_calls: list[str] = []
        self.cancel_calls: list[str] = []

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


def supervisor_with(api: FakeSessionsAPI) -> Supervisor:
    return Supervisor(SimpleNamespace(sessions=api))


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
    assert call["status"] == list(_ACTIVE_STATUSES)  # non-terminal only: what still holds slots
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
