"""Tests for the H Company computer-use integration.

The hai-agents SDK is never called for real here — a fake session client stands in for
it, so these tests assert how we normalize results and wire up the route. The fixtures
mirror what a real h/web-surfer-flash run returns: a finished single-shot task settles to
status "idle" with outcome "success", and the Agent View URL comes from get_session.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

# Make the agent service root importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings  # noqa: E402
from integrations.h_company.client import HClient  # noqa: E402
from integrations.h_company.computer_use import run_browser_task  # noqa: E402
from integrations.h_company.schemas import ComputerUseRequest, SessionResult  # noqa: E402
from main import app  # noqa: E402

# The first real task: research-only, with the guardrails baked into the prompt.
VENUE_RESEARCH_TASK = (
    "Research three venues in San Francisco that could host a 150-person hackathon. "
    "For each venue, compare capacity, neighborhood, pricing, and amenities. "
    "Only gather publicly available information — do not contact vendors, submit forms, "
    "book, or purchase anything."
)


class FakeSessions:
    """Stands in for client.sessions: records get_session calls, returns/raises a preset."""

    def __init__(self, view_url: str | None = None, error: Exception | None = None) -> None:
        self._session = SimpleNamespace(agent_view_url=view_url)
        self._error = error
        self.get_calls: list[str] = []

    def get_session(self, session_id: str) -> object:
        self.get_calls.append(session_id)
        if self._error is not None:
            raise self._error
        return self._session


class FakeSDK:
    """Stands in for hai_agents.Client: records the call and returns or raises a preset."""

    def __init__(
        self,
        result: object = None,
        error: Exception | None = None,
        view_url: str | None = None,
        sessions_error: Exception | None = None,
    ) -> None:
        self._result = result
        self._error = error
        self.sessions = FakeSessions(view_url=view_url, error=sessions_error)
        self.calls: list[dict] = []

    def run_session(self, **kwargs) -> object:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result


def fake_result(**fields) -> SimpleNamespace:
    """A SessionRunResult look-alike; unset fields default to None."""
    defaults = {"id": None, "status": None, "outcome": None, "answer": None, "error": None, "error_code": None}
    return SimpleNamespace(**{**defaults, **fields})


def test_idle_success_is_success() -> None:
    # What a real web-surfer-flash run returns: settled to 'idle', agent self-assessed 'success'.
    sdk = FakeSDK(
        fake_result(id="sess_1", status="idle", outcome="success", answer="Found three venues..."),
        view_url="https://platform.hcompany.ai/agents/sessions/sess_1",
    )
    result = HClient(sdk).run_task(task="hi", agent="h/web-surfer-flash")

    assert result.succeeded is True
    assert result.status == "idle"
    assert result.outcome == "success"
    assert result.answer == "Found three venues..."
    assert result.error is None
    assert result.session_id == "sess_1"
    assert result.agent_view_url == "https://platform.hcompany.ai/agents/sessions/sess_1"
    assert sdk.sessions.get_calls == ["sess_1"]  # URL read from the canonical session record


def test_completed_success() -> None:
    sdk = FakeSDK(fake_result(id="s", status="completed", outcome="success", answer="done"),
                  view_url="https://platform.hcompany.ai/agents/sessions/s")
    result = HClient(sdk).run_task(task="hi", agent="h/web-surfer-flash")

    assert result.succeeded is True
    assert result.status == "completed"
    assert result.agent_view_url.endswith("/s")


def test_completed_without_outcome_is_success() -> None:
    # No self-assessed outcome: fall back to the lifecycle status.
    result = HClient(FakeSDK(fake_result(status="completed", answer="ok"))).run_task(task="hi", agent="h/web-surfer-flash")

    assert result.succeeded is True


def test_blocked_outcome_is_not_success() -> None:
    sdk = FakeSDK(fake_result(status="idle", outcome="blocked", answer="Could not reach the pricing page."))
    result = HClient(sdk).run_task(task="hi", agent="h/web-surfer-flash")

    assert result.succeeded is False
    assert result.outcome == "blocked"
    assert result.answer == "Could not reach the pricing page."


def test_partial_outcome_is_not_success() -> None:
    result = HClient(FakeSDK(fake_result(status="idle", outcome="partial"))).run_task(task="hi", agent="h/web-surfer-flash")

    assert result.succeeded is False
    assert result.outcome == "partial"


def test_failed_session_reports_error() -> None:
    sdk = FakeSDK(fake_result(id="s2", status="failed", error="page crashed", error_code="internal"))
    result = HClient(sdk).run_task(task="hi", agent="h/web-surfer-flash")

    assert result.succeeded is False
    assert result.status == "failed"
    assert result.error == "page crashed (internal)"


def test_timed_out_session() -> None:
    result = HClient(FakeSDK(fake_result(status="timed_out", error_code="timeout"))).run_task(task="hi", agent="h/web-surfer-flash")

    assert result.succeeded is False
    assert result.status == "timed_out"
    assert result.error == "timeout"


def test_interrupted_session() -> None:
    result = HClient(FakeSDK(fake_result(status="interrupted"))).run_task(task="hi", agent="h/web-surfer-flash")

    assert result.succeeded is False
    assert result.status == "interrupted"


def test_sdk_error_becomes_error_result() -> None:
    boom = RuntimeError("connection reset")
    boom.status_code = 503  # mimic hai_agents.core.ApiError carrying an HTTP status
    sdk = FakeSDK(error=boom)
    result = HClient(sdk).run_task(task="hi", agent="h/web-surfer-flash")

    assert result.succeeded is False
    assert result.status == "error"
    assert "503" in result.error
    assert "connection reset" in result.error
    assert sdk.sessions.get_calls == []  # no view-URL fetch after a transport failure


def test_agent_view_url_is_best_effort() -> None:
    # A failed view-URL fetch must not sink an otherwise-good result.
    sdk = FakeSDK(
        fake_result(id="s", status="idle", outcome="success", answer="done"),
        sessions_error=RuntimeError("view fetch failed"),
    )
    result = HClient(sdk).run_task(task="hi", agent="h/web-surfer-flash")

    assert result.succeeded is True
    assert result.agent_view_url is None


def test_run_browser_task_requires_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "")
    # A client whose call would blow up, proving we never reach it without a key.
    guard = FakeSDK(error=AssertionError("SDK must not be called without a key"))
    result = run_browser_task(ComputerUseRequest(task=VENUE_RESEARCH_TASK), client=HClient(guard))

    assert result.succeeded is False
    assert result.status == "error"
    assert "HAI_API_KEY" in result.error
    assert guard.calls == []


def test_run_browser_task_forwards_task_and_agent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(fake_result(id="s9", status="idle", outcome="success", answer="done"))
    result = run_browser_task(ComputerUseRequest(task=VENUE_RESEARCH_TASK), client=HClient(sdk))

    assert result.succeeded is True
    # Called exactly as specified: agent + messages, nothing else.
    assert sdk.calls == [{"agent": "h/web-surfer-flash", "messages": VENUE_RESEARCH_TASK}]


def test_run_endpoint_returns_outcome(monkeypatch) -> None:
    def fake_run(request: ComputerUseRequest) -> SessionResult:
        assert request.task == VENUE_RESEARCH_TASK
        return SessionResult(
            succeeded=True,
            status="idle",
            outcome="success",
            answer="three venues compared",
            session_id="sess_api",
            agent_view_url="https://platform.hcompany.ai/agents/sessions/sess_api",
        )

    monkeypatch.setattr("api.routes.computer_use.run_browser_task", fake_run)
    response = TestClient(app).post("/api/computer-use/run", json={"task": VENUE_RESEARCH_TASK})

    assert response.status_code == 200
    body = response.json()
    assert body["succeeded"] is True
    assert body["status"] == "idle"
    assert body["outcome"] == "success"
    assert body["answer"] == "three venues compared"
    assert body["session_id"] == "sess_api"
    assert body["agent_view_url"].endswith("sess_api")


def test_run_endpoint_rejects_empty_task() -> None:
    response = TestClient(app).post("/api/computer-use/run", json={"task": ""})
    assert response.status_code == 422


def test_health_endpoint() -> None:
    assert TestClient(app).get("/health").json() == {"status": "ok"}
