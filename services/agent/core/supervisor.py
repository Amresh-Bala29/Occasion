"""Supervisor — monitors all running agents and their health.

Read-only oversight of the H sessions behind an event's agents — who is running, how
far along (steps), what failed — plus the account's session-slot quota and a cancel
passthrough. Monitoring is polling-based: H exposes no session webhooks, so callers
poll this surface. Every snapshot carries the session's `agent_view_url`, the
live-view/replay page on the H platform.

Mirrors the service's failure-as-value philosophy: every method returns an honest
report; nothing raises.
"""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)

# Every non-terminal lifecycle state. `idle` still pins a quota slot (one-shot runs
# settle there, carrying their outcome), so hiding it would make the listing disagree
# with the quota numbers and bury runs that need attention.
_ACTIVE_STATUSES: tuple[str, ...] = ("queued", "pending", "running", "paused", "idle", "awaiting_tool_results")

# Terminal states in which a session ended without delivering.
_FAILED_STATUSES: frozenset[str] = frozenset({"failed", "timed_out", "interrupted"})

_KEY_MISSING = "HAI_API_KEY is not configured; set it in services/agent/.env"

_PAGE_SIZE = 50  # comfortably above any slot limit (3 free / 10 developer) plus queue


class SessionSnapshot(BaseModel):
    """One live session as the dashboard needs it: who, what, and where to watch."""

    id: str
    agent: str | None = None
    status: str
    task: str | None = None  # the session's opening user message, verbatim
    agent_view_url: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class QuotaSnapshot(BaseModel):
    """The account's concurrent-session slots."""

    limit: int
    active: int
    available: int


class EventSessionsReport(BaseModel):
    """An event's live sessions plus quota; `succeeded` means the whole report is trustworthy."""

    succeeded: bool
    event_id: str
    sessions: list[SessionSnapshot] = []
    quota: QuotaSnapshot | None = None
    error: str | None = None


class SessionHealth(BaseModel):
    """One session's live status; `succeeded` folds "check reached H" and "session not failed"."""

    succeeded: bool
    session_id: str
    status: str  # lifecycle state, or "error" when the check itself failed
    outcome: str | None = None
    steps: int | None = None
    error: str | None = None
    subagent_session_ids: list[str] = []


class CancelResult(BaseModel):
    succeeded: bool
    session_id: str
    error: str | None = None


class Supervisor:
    """Watches the fleet's H sessions for one deployment of the service.

    `sdk_client` is a hai_agents.Client, or any object exposing `sessions`; tests
    inject fakes through the same seam HClient uses.
    """

    def __init__(self, sdk_client: object) -> None:
        self._sdk = sdk_client

    @classmethod
    def from_settings(cls) -> "Supervisor":
        """Build a client for the session (AGP) host, mirroring HClient.from_settings."""
        from hai_agents import Client

        kwargs: dict[str, str] = {"api_key": settings.hai_api_key}
        if settings.hai_session_base_url:
            kwargs["base_url"] = settings.hai_session_base_url
        return cls(Client(**kwargs))

    def event_sessions(self, event_id: str) -> EventSessionsReport:
        """All non-terminal sessions tagged with this event's group_id, plus quota.

        Partial failures keep whatever was fetched: `succeeded` is True only when both
        H calls worked, and `error` names the one that did not.
        """
        if not settings.hai_api_key:
            return EventSessionsReport(succeeded=False, event_id=event_id, error=_KEY_MISSING)
        sessions: list[SessionSnapshot] = []
        quota: QuotaSnapshot | None = None
        errors: list[str] = []
        try:
            page = self._sdk.sessions.list_sessions(
                group_id=event_id,
                status=list(_ACTIVE_STATUSES),
                size=_PAGE_SIZE,
                sort=["-created_at"],
            )
            sessions = [_snapshot(item) for item in page.items or []]
        except Exception as exc:
            errors.append(f"session listing failed: {_error_message(exc)}")
        try:
            status = self._sdk.sessions.get_session_quota()
            quota = QuotaSnapshot(limit=status.limit, active=status.active, available=status.available)
        except Exception as exc:
            errors.append(f"quota check failed: {_error_message(exc)}")
        if errors:
            logger.warning("event %s: %s", event_id, "; ".join(errors))
        return EventSessionsReport(
            succeeded=not errors,
            event_id=event_id,
            sessions=sessions,
            quota=quota,
            error="; ".join(errors) or None,
        )

    def session_health(self, session_id: str) -> SessionHealth:
        """One session's live status: lifecycle state, progress (steps), and errors."""
        if not settings.hai_api_key:
            return SessionHealth(succeeded=False, session_id=session_id, status="error", error=_KEY_MISSING)
        try:
            status = self._sdk.sessions.get_session_status(session_id)
        except Exception as exc:
            logger.warning("session %s: health check failed: %s", session_id, _error_message(exc))
            return SessionHealth(succeeded=False, session_id=session_id, status="error", error=_error_message(exc))
        lifecycle = _unwrap_str(status.status) or "unknown"
        return SessionHealth(
            succeeded=lifecycle not in _FAILED_STATUSES,
            session_id=session_id,
            status=lifecycle,
            outcome=_unwrap_str(getattr(status, "outcome", None)),
            steps=getattr(status, "steps", None),
            error=_error_text(getattr(status, "error", None), getattr(status, "error_code", None)),
            subagent_session_ids=list(getattr(status, "subagent_session_ids", None) or []),
        )

    def cancel_session(self, session_id: str) -> CancelResult:
        """Stop a runaway or unwanted session (H's DELETE /sessions/{id})."""
        if not settings.hai_api_key:
            return CancelResult(succeeded=False, session_id=session_id, error=_KEY_MISSING)
        try:
            self._sdk.sessions.cancel_session(session_id)
        except Exception as exc:
            logger.warning("session %s: cancel failed: %s", session_id, _error_message(exc))
            return CancelResult(succeeded=False, session_id=session_id, error=_error_message(exc))
        return CancelResult(succeeded=True, session_id=session_id)


def _snapshot(summary: object) -> SessionSnapshot:
    first = getattr(summary, "first_message", None)
    return SessionSnapshot(
        id=str(getattr(summary, "id", "")),
        agent=getattr(summary, "agent", None),
        status=_unwrap_str(getattr(summary, "status", None)) or "unknown",
        task=getattr(first, "message", None),
        agent_view_url=getattr(summary, "agent_view_url", None),
        created_at=getattr(summary, "created_at", None),
        started_at=getattr(summary, "started_at", None),
        finished_at=getattr(summary, "finished_at", None),
    )


def _error_message(exc: Exception) -> str:
    # Mirrors client._result_from_error: keep the HTTP status visible when present.
    message = str(exc).strip() or exc.__class__.__name__
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return f"HTTP {status_code}: {message}"
    return message


def _error_text(error: object, error_code: object) -> str | None:
    # Mirrors client._error_text: one string carrying both the message and the code.
    message = _unwrap_str(error)
    code = _unwrap_str(error_code)
    if message and code:
        return f"{message} ({code})"
    return message or code


def _unwrap_str(value: object) -> str | None:
    # Enums expose their wire value at `.value`; plain strings pass straight through.
    value = getattr(value, "value", value)
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)
