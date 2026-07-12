"""Tests for the H Company computer-use integration and the domain-agent fleet.

The hai-agents SDK is never called for real here — a fake session client stands in for
it, so these tests assert how we normalize results and wire up the route. The fixtures
mirror what a real h/web-surfer-flash run returns: a finished single-shot task settles to
status "idle" with outcome "success", and the Agent View URL comes from get_session.
The domain agents run through the same fake; the Models API is faked with an httpx
MockTransport.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from hai_agents import AnswerValidationError
from hai_agents.types.agent import Agent as HAgentSpec
from pydantic import BaseModel

# Make the agent service root importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.budget_agent import BudgetAgent  # noqa: E402
from agents.catering_agent import CateringAgent  # noqa: E402
from agents.decorations_agent import DecorationsAgent  # noqa: E402
from agents.distribution_agent import DistributionAgent  # noqa: E402
from agents.entertainment_agent import EntertainmentAgent  # noqa: E402
from agents.marketing_agent import MarketingAgent  # noqa: E402
from agents.merchandise_agent import MerchandiseAgent  # noqa: E402
from agents.post_event_agent import PostEventAgent  # noqa: E402
from agents.purchasing_agent import PurchasingAgent  # noqa: E402
from agents.requirements_agent import EventRequirements, RequirementsAgent  # noqa: E402
from agents.scheduling_agent import SchedulingAgent  # noqa: E402
from agents.staffing_agent import StaffingAgent  # noqa: E402
from agents.venue_agent import VenueAgent, VenueResearch  # noqa: E402
from core.config import settings  # noqa: E402
from integrations.h_company.client import HClient  # noqa: E402
from integrations.h_company.computer_use import run_browser_task  # noqa: E402
from integrations.h_company.schemas import (  # noqa: E402
    MODEL_DEEP,
    MODEL_FAST,
    ComputerUseRequest,
    SessionResult,
)
from main import app  # noqa: E402
from models.task import Task  # noqa: E402

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


def test_from_settings_defaults_to_sdk_region(monkeypatch) -> None:
    # No session base configured: the SDK's own default region (EU AGP host) must win —
    # the Models API host must never leak into session calls (it 404s them).
    recorded: list[dict] = []

    class RecordingClient:
        def __init__(self, **kwargs) -> None:
            recorded.append(kwargs)

    monkeypatch.setattr("hai_agents.Client", RecordingClient)
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    monkeypatch.setattr(settings, "hai_session_base_url", "")
    HClient.from_settings()

    assert recorded == [{"api_key": "hk-test"}]


def test_from_settings_honors_session_base_url(monkeypatch) -> None:
    recorded: list[dict] = []

    class RecordingClient:
        def __init__(self, **kwargs) -> None:
            recorded.append(kwargs)

    monkeypatch.setattr("hai_agents.Client", RecordingClient)
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    monkeypatch.setattr(settings, "hai_session_base_url", "https://agp.hcompany.ai")
    HClient.from_settings()

    assert recorded == [{"api_key": "hk-test", "base_url": "https://agp.hcompany.ai"}]


def test_run_browser_task_requires_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "")
    # A client whose call would blow up, proving we never reach it without a key.
    guard = FakeSDK(error=AssertionError("SDK must not be called without a key"))
    result = run_browser_task(ComputerUseRequest(task=VENUE_RESEARCH_TASK), client=HClient(guard))

    assert result.succeeded is False
    assert result.status == "error"
    assert "HAI_API_KEY" in result.error
    assert guard.calls == []


def test_run_browser_task_forwards_task_agent_and_browser(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(fake_result(id="s9", status="idle", outcome="success", answer="done"))
    result = run_browser_task(ComputerUseRequest(task=VENUE_RESEARCH_TASK), client=HClient(sdk))

    assert result.succeeded is True
    # Forwards the task/agent, plus the browser overrides that point H at a real cloud Chrome
    # opened at Google with a reused, signed-in profile.
    assert len(sdk.calls) == 1
    call = sdk.calls[0]
    assert call["agent"] == "h/web-surfer-flash"
    assert call["messages"] == VENUE_RESEARCH_TASK
    overrides = call["overrides"]
    assert overrides["agent.environments[kind=web].host"] == "cloud"
    assert overrides["agent.environments[kind=web].start_url"] == "https://www.google.com"
    assert overrides["agent.environments[kind=web].use_default_browser_profile"] is True
    assert overrides["agent.environments[kind=web].persist_browser_profile"] is True


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


# --- Domain-agent fleet: inline agents, structured answers, and the Models API ---

BROWSER_AGENTS = [
    VenueAgent,
    CateringAgent,
    StaffingAgent,
    EntertainmentAgent,
    MerchandiseAgent,
    DecorationsAgent,
    PurchasingAgent,
    MarketingAgent,
    PostEventAgent,
    BudgetAgent,
    SchedulingAgent,
    DistributionAgent,
]


class _Findings(BaseModel):
    """Minimal answer schema for structured-output tests."""

    items: list[str]


def test_run_task_inline_agent_forwards_spec_without_overrides() -> None:
    sdk = FakeSDK(fake_result(id="s", status="idle", outcome="success", answer="ok"))
    spec = {
        "name": "occasion-venue",
        "description": "d",
        "model": MODEL_DEEP,
        "instructions": "i",
        "environments": [{"kind": "web", "id": "browser"}],
    }
    result = HClient(sdk).run_task(task="hi", agent=spec, max_steps=5, max_time_s=60, group_id="evt-1")

    assert result.succeeded is True
    call = sdk.calls[0]
    assert call["agent"] is spec
    # Browser overrides target agent.environments[kind=web] and would clobber an inline
    # agent's own environment, so they must stay off the inline path.
    assert "overrides" not in call
    assert call["max_steps"] == 5
    assert call["max_time_s"] == 60
    assert call["group_id"] == "evt-1"


def test_answer_schema_returns_validated_data() -> None:
    sdk = FakeSDK(fake_result(id="s", status="idle", outcome="success", answer=_Findings(items=["a"])))
    result = HClient(sdk).run_task(task="hi", agent="h/web-surfer-flash", answer_schema=_Findings)

    assert sdk.calls[0]["answer_schema"] is _Findings
    assert result.succeeded is True
    assert result.data == {"items": ["a"]}
    assert result.answer is None  # one authoritative representation: data


def test_answer_validation_error_is_honest_failure() -> None:
    boom = AnswerValidationError("raw payload", _Findings, ValueError("items missing"))
    result = HClient(FakeSDK(error=boom)).run_task(
        task="hi", agent="h/web-surfer-flash", answer_schema=_Findings
    )

    assert result.succeeded is False
    assert result.status == "error"
    assert result.answer == "raw payload"  # the raw wire value is preserved, not dropped
    assert "_Findings" in result.error


def test_domain_agent_runs_inline_session(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(fake_result(id="s", status="idle", outcome="success", answer=None))
    task = Task(id="t1", event_id="evt-42", title="Research three venues")
    result = asyncio.run(VenueAgent(client=HClient(sdk)).run(task))

    assert result.succeeded is True
    call = sdk.calls[0]
    assert call["messages"] == "Research three venues (event: evt-42)"
    assert call["agent"]["name"] == "occasion-venue"
    assert "approval was granted" in call["agent"]["instructions"]  # shared guardrails
    assert call["answer_schema"] is VenueResearch
    assert call["max_time_s"] == 2400
    assert call["max_steps"] == 80
    assert call["group_id"] == "evt-42"
    assert "overrides" not in call


def test_domain_agent_run_requires_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "")
    guard = FakeSDK(error=AssertionError("SDK must not be called without a key"))
    result = asyncio.run(VenueAgent(client=HClient(guard)).run("research venues"))

    assert result.succeeded is False
    assert result.status == "error"
    assert "HAI_API_KEY" in result.error
    assert guard.calls == []


def test_agent_specs_are_wire_valid() -> None:
    # One loop guards all 12 browser-agent configs against drift: H's name format, a
    # known model, and the run bound that keeps a session from blocking forever.
    for agent_class in BROWSER_AGENTS:
        spec = agent_class().agent_spec()
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]*[a-z0-9]", spec["name"]), spec["name"]
        assert spec["model"] in {MODEL_DEEP, MODEL_FAST}
        assert spec["description"]
        assert spec["environments"][0]["kind"] == "web"
        assert agent_class.answer_schema is not None
        assert agent_class.max_time_s is not None
        HAgentSpec.model_validate(spec)  # the SDK's own wire model accepts the spec
    # The requirements agent is browserless (Models API), so it carries no browser spec.
    assert RequirementsAgent.answer_schema is EventRequirements
    assert RequirementsAgent.model == MODEL_DEEP


def test_requirements_agent_extracts_requirements(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    monkeypatch.setattr(settings, "hai_models_base_url", "https://models.test/v1")
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        content = json.dumps(
            {"event_type": "conference", "headcount": 150, "open_questions": ["What is the budget?"]}
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    http_client = httpx.Client(transport=httpx.MockTransport(respond))
    agent = RequirementsAgent(http_client=http_client)
    result = asyncio.run(agent.run("Client: we're planning a conference for about 150 people."))

    assert result.succeeded is True
    assert result.status == "completed"
    assert result.data["event_type"] == "conference"
    assert result.data["headcount"] == 150
    assert result.data["open_questions"] == ["What is the budget?"]
    request = seen[0]
    # The full URL proves completions target the Models host, not the sessions host.
    assert str(request.url) == "https://models.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer hk-test"
    body = json.loads(request.content)
    assert body["model"] == MODEL_DEEP
    assert body["structured_outputs"]["json"]["title"] == "EventRequirements"


def test_requirements_agent_reports_malformed_content(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    http_client = httpx.Client(transport=httpx.MockTransport(respond))
    result = asyncio.run(RequirementsAgent(http_client=http_client).run("hello"))

    assert result.succeeded is False
    assert result.status == "error"
    assert result.answer == "not json"  # raw content preserved for debugging
    assert result.error
