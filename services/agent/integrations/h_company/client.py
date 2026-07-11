"""H Company API client.

A thin adapter over the `hai-agents` SDK. It runs one managed computer-use session and
normalizes the SDK result into our own `SessionResult`, keeping every detail of the SDK's
field names and status vocabulary in this one place.
"""

from __future__ import annotations

from core.config import settings
from integrations.h_company.schemas import SessionResult

_COMPLETED = "completed"
_SUCCESS = "success"


class HClient:
    """Runs managed computer-use sessions on H Company."""

    def __init__(self, sdk_client: object) -> None:
        # `sdk_client` is a hai_agents.Client, or any object exposing run_session/sessions.
        self._sdk = sdk_client

    @classmethod
    def from_settings(cls) -> "HClient":
        """Build a client from configured credentials.

        The SDK is imported lazily so the package is only needed when a real session
        actually runs; tests inject a double and never reach this path.
        """
        from hai_agents import Client

        kwargs: dict[str, str] = {"api_key": settings.hai_api_key}
        if settings.hai_base_url:
            kwargs["base_url"] = settings.hai_base_url
        return cls(Client(**kwargs))

    def run_task(self, task: str, agent: str) -> SessionResult:
        """Run one task to completion and return an honest result.

        The SDK blocks until the session settles. A session that fails, times out, or is
        blocked comes back as a normal result (never raised); only transport-level errors
        reach the except branch.
        """
        try:
            result = self._sdk.run_session(agent=agent, messages=task)
        except Exception as exc:  # auth, rate limit, network — surface it, don't crash
            return _result_from_error(exc)
        return _result_from_session(result, self._agent_view_url(getattr(result, "id", None)))

    def _agent_view_url(self, session_id: str | None) -> str | None:
        """Fetch the canonical Agent View link from the session record.

        run_session does not carry this URL (and the flash agent emits no live-view event),
        so we read it from the session. Best-effort: a fetch failure must not sink the run.
        """
        if not session_id:
            return None
        try:
            session = self._sdk.sessions.get_session(session_id)
        except Exception:
            return None
        return _as_optional_str(getattr(session, "agent_view_url", None))


def _result_from_session(result: object, agent_view_url: str | None) -> SessionResult:
    status = _as_optional_str(_unwrap(getattr(result, "status", None))) or "unknown"
    outcome = _as_optional_str(_unwrap(getattr(result, "outcome", None)))
    return SessionResult(
        succeeded=_succeeded(status, outcome),
        status=status,
        outcome=outcome,
        answer=_as_optional_str(getattr(result, "answer", None)),
        error=_error_text(getattr(result, "error", None), getattr(result, "error_code", None)),
        session_id=_as_optional_str(getattr(result, "id", None)),
        agent_view_url=agent_view_url,
    )


def _succeeded(status: str, outcome: str | None) -> bool:
    # The agent's self-assessed outcome is authoritative when present: a single-shot task
    # settles to 'idle' with outcome 'success', not 'completed'. Without an outcome (e.g. a
    # failed or timed-out run), fall back to the lifecycle status.
    if outcome is not None:
        return outcome == _SUCCESS
    return status == _COMPLETED


def _result_from_error(exc: Exception) -> SessionResult:
    message = str(exc).strip() or exc.__class__.__name__
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        message = f"HTTP {status_code}: {message}"
    return SessionResult(succeeded=False, status="error", error=message)


def _error_text(error: object, error_code: object) -> str | None:
    message = _as_optional_str(error)
    code = _as_optional_str(_unwrap(error_code))
    if message and code:
        return f"{message} ({code})"
    return message or code


def _unwrap(value: object) -> object:
    # Enums expose their wire value at `.value`; plain strings pass straight through.
    return getattr(value, "value", value)


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)
