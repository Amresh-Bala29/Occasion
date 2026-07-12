"""Tests for the chat and run-polling API.

Routes are exercised through TestClient with a fake run manager (and repository)
swapped in via dependency override, so no H account or database is required. The
focus is the async seam: POST /chat hands the message to the manager and returns
the running record; GET /runs/{id} is the polling contract, snake_case like every
agentic surface.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from api.dependencies import get_run_manager, get_run_repository  # noqa: E402
from database.repositories.run_repository import RunRecord  # noqa: E402
from integrations.h_company.schemas import SessionResult  # noqa: E402
from main import app  # noqa: E402

EVENT_ID = "novaflow-summit-2026"


def _running(message: str, event_id: str | None) -> RunRecord:
    return RunRecord(id="run-abc123", event_id=event_id, kind="chat", title=message, status="running")


def _settled() -> RunRecord:
    return RunRecord(
        id="run-abc123",
        event_id=EVENT_ID,
        kind="chat",
        title="Find a venue",
        status="completed",
        agent="requirements",
        reason="fits the brief",
        result=SessionResult(succeeded=True, status="completed", answer="ok"),
    )


class FakeRunManager:
    def __init__(self) -> None:
        self.chats: list[tuple[str, str | None]] = []
        self.bookings: list[tuple[dict, str]] = []

    def start_chat(self, message: str, event_id: str | None) -> RunRecord:
        self.chats.append((message, event_id))
        return _running(message, event_id)

    def start_booking(self, action: dict, *, approval_note: str) -> RunRecord:
        self.bookings.append((action, approval_note))
        return RunRecord(
            id="run-book1", event_id=action.get("event_id"), kind="booking", title="Book", status="running"
        )


class FakeRunRepo:
    def __init__(self, record: RunRecord | None) -> None:
        self._record = record

    def get(self, run_id: str) -> RunRecord | None:
        return self._record if self._record and run_id == self._record.id else None


def _client(manager: FakeRunManager) -> TestClient:
    app.dependency_overrides[get_run_manager] = lambda: manager
    return TestClient(app)


def _polling_client(record: RunRecord | None) -> TestClient:
    app.dependency_overrides[get_run_repository] = lambda: FakeRunRepo(record)
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_chat_starts_run_and_returns_running_record() -> None:
    manager = FakeRunManager()
    body = _client(manager).post("/chat", json={"message": "Find a venue", "event_id": EVENT_ID}).json()

    assert manager.chats == [("Find a venue", EVENT_ID)]
    assert body["id"] == "run-abc123"
    assert body["status"] == "running"
    assert body["kind"] == "chat"
    assert body["result"] is None  # not settled yet


def test_plain_chat_passes_no_event() -> None:
    manager = FakeRunManager()
    _client(manager).post("/chat", json={"message": "What can you do?"})

    assert manager.chats == [("What can you do?", None)]


def test_empty_message_is_422() -> None:
    response = _client(FakeRunManager()).post("/chat", json={"message": ""})
    assert response.status_code == 422


def test_get_run_returns_snake_case_settled_record() -> None:
    body = _polling_client(_settled()).get("/runs/run-abc123").json()

    assert body["status"] == "completed"
    assert body["agent"] == "requirements"
    assert body["reason"] == "fits the brief"
    assert body["result"]["succeeded"] is True
    assert body["result"]["answer"] == "ok"
    assert "taskId" not in body  # agentic surfaces stay snake_case, like SessionResult


def test_get_missing_run_is_404() -> None:
    response = _polling_client(None).get("/runs/run-unknown")
    assert response.status_code == 404
