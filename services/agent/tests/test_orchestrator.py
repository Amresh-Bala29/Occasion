"""Tests for the orchestrator: routing, dispatch, and bounded fan-out.

Nothing here talks to H for real. Browser sessions run against a fake SDK injected
through HClient, and the Models API (routing and the requirements agent) is faked with
an httpx MockTransport that records every request — so the tests can assert not just
what came back but which paths were consulted at all.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

# Make the agent service root importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.base_agent import BaseAgent  # noqa: E402
from core.config import settings  # noqa: E402
from core.orchestrator import (  # noqa: E402
    BUILTIN_AGENTS,
    BUILTIN_MAX_TIME_S,
    DOMAIN_AGENTS,
    ROSTER_NAMES,
    ROUTING_INSTRUCTIONS,
    WORKFLOWS,
    Orchestrator,
)
from integrations.h_company.client import HClient  # noqa: E402
from integrations.h_company.schemas import DEFAULT_AGENT, MODEL_DEEP, MODEL_FAST  # noqa: E402
from models.task import Task  # noqa: E402


class FakeSDK:
    """Stands in for hai_agents.Client: records run_session calls, returns a preset.

    Deliberately has no `sessions` attribute — HClient's agent-view fetch is best-effort
    and treats the missing attribute as "no URL", which keeps this fake minimal.
    """

    def __init__(self, result: object = None) -> None:
        self._result = result
        self.calls: list[dict] = []

    def run_session(self, **kwargs) -> object:
        self.calls.append(kwargs)
        return self._result


class CountingSDK(FakeSDK):
    """A FakeSDK whose run_session sleeps briefly and tracks peak concurrent occupancy."""

    def __init__(self) -> None:
        super().__init__(fake_result(status="idle", outcome="success", answer="done"))
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0

    def run_session(self, **kwargs) -> object:
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)
        time.sleep(0.02)
        with self._lock:
            self._active -= 1
        return super().run_session(**kwargs)


def fake_result(**fields) -> SimpleNamespace:
    """A SessionRunResult look-alike; unset fields default to None."""
    defaults = {"id": None, "status": None, "outcome": None, "answer": None, "error": None, "error_code": None}
    return SimpleNamespace(**{**defaults, **fields})


def completion_client(content: dict) -> tuple[httpx.Client, list[httpx.Request]]:
    """A Models API double: serves `content` as the completion answer, records requests."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    return httpx.Client(transport=httpx.MockTransport(respond)), requests


def failing_completion_client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500, text="boom")))


def make_task(**overrides) -> Task:
    """A fresh Task per test — the orchestrator records routing decisions on it."""
    fields: dict = {"id": "t1", "event_id": "evt-9", "title": "Find a venue for 150 people"}
    fields.update(overrides)
    return Task(**fields)


def test_registry_covers_the_whole_fleet() -> None:
    expected = {
        "requirements",
        "venue",
        "catering",
        "staffing",
        "entertainment",
        "decorations",
        "merchandise",
        "purchasing",
        "scheduling",
        "budget",
        "marketing",
        "distribution",
        "post_event",
    }
    assert set(DOMAIN_AGENTS) == expected
    assert all(issubclass(cls, BaseAgent) for cls in DOMAIN_AGENTS.values())
    # The router reads each description; an empty one would make its agent unroutable.
    assert all(cls.description for cls in DOMAIN_AGENTS.values())
    assert {DEFAULT_AGENT, "h/web-scraper-flash", "h/deep-search-pro"} <= ROSTER_NAMES
    assert set(WORKFLOWS) == {"workflow/event_planning", "workflow/vendor_sourcing", "workflow/vendor_outreach"}
    assert set(WORKFLOWS) <= ROSTER_NAMES


def test_routing_instructions_list_every_agent() -> None:
    for cls in DOMAIN_AGENTS.values():
        assert f"- {cls.name}: {cls.description}" in ROUTING_INSTRUCTIONS
    for agent_id, description in BUILTIN_AGENTS.items():
        assert f"- {agent_id}: {description}" in ROUTING_INSTRUCTIONS
    for name, description in WORKFLOWS.items():
        assert f"- {name}: {description}" in ROUTING_INSTRUCTIONS


def test_explicit_assignee_skips_routing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(fake_result(id="s1", status="idle", outcome="success", answer="found venues"))
    http, requests = completion_client({"reason": "unused", "agent": "budget"})
    task = make_task(assignee_agent="venue")

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task(task))

    assert run.task_id == "t1"
    assert run.agent == "venue"
    assert run.reason is None
    assert run.result.succeeded is True
    (call,) = sdk.calls
    assert call["agent"]["name"] == "occasion-venue"
    assert call["group_id"] == "evt-9"
    assert requests == []  # the router was never consulted


def test_unknown_explicit_assignee_is_error_result() -> None:
    sdk = FakeSDK()
    http, requests = completion_client({"reason": "unused", "agent": "venue"})
    task = make_task(assignee_agent="florist")

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task(task))

    assert run.agent is None
    assert run.result.succeeded is False
    assert "florist" in run.result.error
    assert sdk.calls == []
    assert requests == []
    # The bad assignment stays visible on the task instead of being rerouted away.
    assert task.assignee_agent == "florist"


def test_unassigned_task_routes_and_records_decision(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(fake_result(status="idle", outcome="success", answer="menus planned"))
    http, requests = completion_client({"reason": "food task", "agent": "catering"})
    task = make_task(title="Plan menus for 150 guests")

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task(task))

    assert run.agent == "catering"
    assert run.reason == "food task"
    assert task.assignee_agent == "catering"
    (call,) = sdk.calls
    assert call["agent"]["name"] == "occasion-catering"
    (request,) = requests
    body = json.loads(request.content)
    assert body["model"] == MODEL_FAST
    assert body["messages"][0]["content"] == ROUTING_INSTRUCTIONS
    # The router sees the same rendering the agent will get.
    assert "Plan menus for 150 guests" in body["messages"][1]["content"]
    assert "evt-9" in body["messages"][1]["content"]


def test_route_to_builtin_runs_managed_agent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(fake_result(status="idle", outcome="success", answer="AV costs summarized"))
    http, _ = completion_client({"reason": "broad research", "agent": "h/deep-search-pro"})
    task = make_task(title="What do hackathons typically spend on AV?")

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task(task))

    assert run.agent == "h/deep-search-pro"
    assert task.assignee_agent == "h/deep-search-pro"
    (call,) = sdk.calls
    assert call["agent"] == "h/deep-search-pro"  # a string: the managed path
    assert "overrides" in call  # which carries the signed-in browser overrides
    assert call["max_time_s"] == BUILTIN_MAX_TIME_S
    assert call["group_id"] == "evt-9"


def test_unknown_routed_name_falls_back_to_default_agent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(fake_result(status="idle", outcome="success", answer="handled"))
    http, _ = completion_client({"reason": "made up", "agent": "concierge"})
    task = make_task()

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task(task))

    assert run.agent == DEFAULT_AGENT
    assert "concierge" in run.reason
    assert task.assignee_agent == DEFAULT_AGENT
    (call,) = sdk.calls
    assert call["agent"] == DEFAULT_AGENT


def test_near_miss_workflow_name_falls_back_to_default_agent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK(fake_result(status="idle", outcome="success", answer="browsed"))
    # The router dropping the workflow/ prefix is the plausible near-miss.
    http, _ = completion_client({"reason": "plan it all", "agent": "event_planning"})
    task = make_task(title="Plan the entire company offsite")

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task(task))

    assert run.agent == DEFAULT_AGENT
    assert "event_planning" in run.reason
    (call,) = sdk.calls
    assert call["agent"] == DEFAULT_AGENT


def test_plain_string_task_cannot_run_a_workflow(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK()
    http, requests = completion_client({"reason": "full event ask", "agent": "workflow/event_planning"})

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=http).run_task("plan our whole offsite"))

    assert run.agent == "workflow/event_planning"
    assert run.result.succeeded is False
    assert "event-scoped Task" in run.result.error
    assert len(requests) == 1  # only the routing call; the chain never started
    assert sdk.calls == []


def test_routing_failure_is_error_result(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = FakeSDK()
    task = make_task()

    run = asyncio.run(Orchestrator(client=HClient(sdk), http_client=failing_completion_client()).run_task(task))

    assert run.agent is None
    assert run.result.succeeded is False
    assert run.result.error
    assert sdk.calls == []
    assert task.assignee_agent is None


def test_missing_api_key_fails_routing_honestly(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "")
    http, requests = completion_client({"reason": "unused", "agent": "venue"})

    run = asyncio.run(Orchestrator(client=HClient(FakeSDK()), http_client=http).run_task("book a dj"))

    assert run.task_id is None  # plain-string tasks carry no id
    assert run.agent is None
    assert run.result.succeeded is False
    assert "HAI_API_KEY" in run.result.error
    assert requests == []  # the key guard fires before any HTTP


def test_missing_api_key_still_honest_for_builtin_assignee(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "")
    sdk = FakeSDK()
    task = make_task(assignee_agent="h/web-scraper-flash")

    run = asyncio.run(Orchestrator(client=HClient(sdk)).run_task(task))

    assert run.agent == "h/web-scraper-flash"  # dispatch was attempted; its own guard answered
    assert run.result.succeeded is False
    assert "HAI_API_KEY" in run.result.error
    assert sdk.calls == []


def test_requirements_assignee_uses_models_api(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    http, requests = completion_client({"event_type": "hackathon", "headcount": 150})
    task = make_task(assignee_agent="requirements", title="Transcript: we want a 150-person hackathon")

    # No browser client at all: the requirements agent must not need one.
    run = asyncio.run(Orchestrator(http_client=http).run_task(task))

    assert run.agent == "requirements"
    assert run.result.succeeded is True
    assert run.result.data["event_type"] == "hackathon"
    assert run.result.data["headcount"] == 150
    (request,) = requests
    body = json.loads(request.content)
    assert body["model"] == MODEL_DEEP  # the agent's own model, not the router's fast one


def test_run_tasks_caps_concurrency_and_keeps_order(monkeypatch) -> None:
    monkeypatch.setattr(settings, "hai_api_key", "hk-test")
    sdk = CountingSDK()
    tasks = [make_task(id=f"t{i}", title=f"Venue sweep {i}", assignee_agent="venue") for i in range(5)]

    runs = asyncio.run(Orchestrator(client=HClient(sdk)).run_tasks(tasks, limit=2))

    assert [run.task_id for run in runs] == ["t0", "t1", "t2", "t3", "t4"]
    assert all(run.result.succeeded for run in runs)
    assert len(sdk.calls) == 5
    assert sdk.peak <= 2


def test_run_tasks_rejects_nonpositive_limit() -> None:
    with pytest.raises(ValueError):
        asyncio.run(Orchestrator().run_tasks(["anything"], limit=0))
