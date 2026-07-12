"""H Company API client.

A thin adapter over H's two inference surfaces: computer-use sessions via the
`hai-agents` SDK (HClient) and browserless chat completions via the OpenAI-compatible
Models API (run_structured_completion). Both normalize into our own `SessionResult`,
keeping every detail of H's field names and status vocabulary in this one place.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx
from hai_agents import AnswerValidationError
from pydantic import BaseModel, ValidationError

from core.config import settings
from integrations.h_company.schemas import MODEL_DEEP, SessionResult
from integrations.h_company.session import browser_overrides

logger = logging.getLogger(__name__)

_COMPLETED = "completed"
_SUCCESS = "success"

# Statuses under which a fetched session's latest_answer is final. A one-shot run
# settles to idle carrying its outcome; completed is the fully closed state.
_SETTLED_STATUSES = frozenset({_COMPLETED, "idle"})

_COMPLETION_TIMEOUT_S = 120.0


class HClient:
    """Runs managed computer-use sessions on H Company."""

    def __init__(self, sdk_client: object) -> None:
        # `sdk_client` is a hai_agents.Client, or any object exposing run_session/sessions.
        self._sdk = sdk_client

    @classmethod
    def from_settings(cls) -> "HClient":
        """Build a client from configured credentials.

        The SDK client is only constructed when a real session runs; tests inject a
        double and never reach this path.
        """
        from hai_agents import Client

        kwargs: dict[str, str] = {"api_key": settings.hai_api_key}
        if settings.hai_session_base_url:
            kwargs["base_url"] = settings.hai_session_base_url
        return cls(Client(**kwargs))

    def run_task(
        self,
        task: str,
        agent: str | dict,
        *,
        answer_schema: type[BaseModel] | None = None,
        max_steps: int | None = None,
        max_time_s: float | None = None,
        group_id: str | None = None,
    ) -> SessionResult:
        """Run one task to completion and return an honest result.

        `agent` is a managed-agent id or a full inline agent definition. The SDK blocks
        until the session settles (`max_time_s` is the real bound — without it a stuck
        session blocks indefinitely). A session that fails, times out, or is blocked
        comes back as a normal result (never raised); only transport-level errors reach
        the except branch.
        """
        kwargs: dict[str, object] = {"agent": agent, "messages": task}
        if isinstance(agent, str):
            # Override selectors like agent.environments[kind=web] would also match an
            # inline agent's environment and clobber its per-agent start_url, so the
            # browser overrides stay on the managed-agent path only.
            kwargs["overrides"] = browser_overrides()
        if answer_schema is not None:
            kwargs["answer_schema"] = answer_schema
        if max_steps is not None:
            kwargs["max_steps"] = max_steps
        if max_time_s is not None:
            kwargs["max_time_s"] = max_time_s
        if group_id is not None:
            kwargs["group_id"] = group_id
        try:
            result = self._sdk.run_session(**kwargs)
        except AnswerValidationError as exc:
            # The run finished but its final answer failed schema validation. The
            # exception carries only the raw payload — no session id or status.
            return SessionResult(
                succeeded=False,
                status="error",
                answer=_as_optional_str(exc.raw),
                error=str(exc),
            )
        except Exception as exc:  # auth, rate limit, network — surface it, don't crash
            return _result_from_error(exc)
        return _result_from_session(result, self._agent_view_url(getattr(result, "id", None)))

    def completed_research(self, event_id: str, categories: Sequence[str]) -> dict[str, SessionResult]:
        """The newest settled research session's final answer, per category.

        The recovery path for runs this process lost: research sessions live on under
        the event's group_id, named occasion-<category> (BaseAgent.agent_spec), and a
        settled session's `latest_answer` still carries the schema answer. Blocking
        (SDK calls) — callers hop threads exactly like run_task. Best-effort: a listing
        failure returns {}, a single session fetch failure skips that category.
        """
        try:
            page = self._sdk.sessions.list_sessions(group_id=event_id, size=50, sort=["-created_at"])
        except Exception as exc:
            logger.warning("event %s: session listing failed during recovery: %s", event_id, exc)
            return {}
        wanted = {f"occasion-{category}": category for category in categories}
        results: dict[str, SessionResult] = {}
        for summary in getattr(page, "items", None) or []:
            category = wanted.get(getattr(summary, "agent", None) or "")
            if category is None or category in results:
                continue
            status = _as_optional_str(_unwrap(getattr(summary, "status", None)))
            if status not in _SETTLED_STATUSES:
                continue
            try:
                session = self._sdk.sessions.get_session(summary.id)
            except Exception as exc:
                logger.warning("session %s: fetch failed during recovery: %s", summary.id, exc)
                continue
            result = _result_from_recovered_session(session)
            # An answerless session recovers nothing; leave the slot open for an older one.
            if result.data is not None or result.answer:
                results[category] = result
        return results

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
    answer_value = getattr(result, "answer", None)
    data: dict | None = None
    answer: str | None = None
    if isinstance(answer_value, BaseModel):
        # A schema-validated answer: one authoritative representation, in `data`.
        data = answer_value.model_dump(mode="json")
    else:
        answer = _as_optional_str(answer_value)
    return SessionResult(
        succeeded=_succeeded(status, outcome),
        status=status,
        outcome=outcome,
        answer=answer,
        data=data,
        error=_error_text(getattr(result, "error", None), getattr(result, "error_code", None)),
        session_id=_as_optional_str(getattr(result, "id", None)),
        agent_view_url=agent_view_url,
    )


def _result_from_recovered_session(session: object) -> SessionResult:
    """A settled session fetched back from H, normalized like a live run's result.

    `latest_answer` mirrors run_session's answer: a dict when the session ran with an
    answer schema (already the schema's JSON dump), free text otherwise. Status and
    outcome live on the session's nested status record.
    """
    status_record = getattr(session, "status", None)
    status = _as_optional_str(_unwrap(getattr(status_record, "status", None))) or "unknown"
    outcome = _as_optional_str(_unwrap(getattr(status_record, "outcome", None)))
    answer_value = getattr(session, "latest_answer", None)
    data = answer_value if isinstance(answer_value, dict) else None
    answer = None if isinstance(answer_value, dict) else _as_optional_str(answer_value)
    return SessionResult(
        succeeded=_succeeded(status, outcome),
        status=status,
        outcome=outcome,
        answer=answer,
        data=data,
        error=_error_text(getattr(status_record, "error", None), getattr(status_record, "error_code", None)),
        session_id=_as_optional_str(getattr(session, "id", None)),
        agent_view_url=_as_optional_str(getattr(session, "agent_view_url", None)),
    )


def _succeeded(status: str, outcome: str | None) -> bool:
    # The agent's self-assessed outcome is authoritative when present: a single-shot task
    # settles to 'idle' with outcome 'success', not 'completed'. Without an outcome (e.g. a
    # failed or timed-out run), fall back to the lifecycle status.
    if outcome is not None:
        return outcome == _SUCCESS
    return status == _COMPLETED


def run_structured_completion(
    prompt: str,
    instructions: str,
    schema: type[BaseModel],
    *,
    model: str = MODEL_DEEP,
    http_client: httpx.Client | None = None,
) -> SessionResult:
    """Run one browserless Holo chat completion, validated against `schema`.

    The Models API is H's OpenAI-compatible inference endpoint; `structured_outputs` is
    its constrained-JSON parameter, so the reply parses into `schema` by construction.
    For agents whose work is pure reasoning over text — no browser session involved.
    Failures come back as honest results, never raised, matching run_task.
    """
    if not settings.hai_api_key:
        return SessionResult(
            succeeded=False,
            status="error",
            error="HAI_API_KEY is not configured; set it in services/agent/.env",
        )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": prompt},
        ],
        # Extraction should be reproducible, not creative.
        "temperature": 0.2,
        "structured_outputs": {"json": schema.model_json_schema()},
    }
    base_url = settings.hai_models_base_url.rstrip("/")
    request = {
        "url": f"{base_url}/chat/completions",
        "headers": {"Authorization": f"Bearer {settings.hai_api_key}"},
        "json": body,
    }
    try:
        if http_client is not None:
            response = http_client.post(**request)
        else:
            with httpx.Client(timeout=_COMPLETION_TIMEOUT_S) as client:
                response = client.post(**request)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # transport failure, HTTP error status, or non-JSON body
        return _result_from_error(exc)
    content = _completion_content(payload)
    if content is None:
        return SessionResult(
            succeeded=False,
            status="error",
            error="Models API response carried no message content",
        )
    try:
        validated = schema.model_validate_json(content)
    except ValidationError as exc:
        return SessionResult(succeeded=False, status="error", answer=content, error=str(exc))
    return SessionResult(
        succeeded=True,
        status="completed",
        answer=content,
        data=validated.model_dump(mode="json"),
    )


def _completion_content(payload: object) -> str | None:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return content if isinstance(content, str) else None


def _result_from_error(exc: Exception) -> SessionResult:
    message = str(exc).strip() or exc.__class__.__name__
    # The SDK's ApiError carries the status on the exception; httpx.HTTPStatusError
    # carries it on the response. Prefix it either way so 401/429/500 read clearly.
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
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
