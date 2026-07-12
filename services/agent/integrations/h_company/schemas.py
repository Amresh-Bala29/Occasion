"""Request/response schemas for the H Company integration."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Managed computer-use agent used for browser research tasks.
DEFAULT_AGENT = "h/web-surfer-flash"

# Holo models for inline domain agents. Deep is the strongest multi-step reasoner with a
# 32K output ceiling; Fast trades depth for latency and caps output at 4K tokens, so it
# only suits procedural flows with compact structured answers.
MODEL_DEEP = "holo3-122b-a10b"
MODEL_FAST = "holo3-1-35b-a3b"


class ComputerUseRequest(BaseModel):
    """A natural-language task to run through the managed computer-use agent."""

    task: str = Field(..., min_length=1, description="What the agent should do, in plain language.")
    agent: str = Field(DEFAULT_AGENT, description="Managed agent id to run the task on.")


class SessionResult(BaseModel):
    """The honest result of one computer-use session.

    `succeeded` is the field to branch on. `status` is the run's lifecycle state from the
    SDK (completed, failed, timed_out, interrupted, or idle — a finished single-shot task
    often settles to "idle" while awaiting a possible follow-up), or "error" when the call
    never produced a session. `outcome` is the agent's own assessment of its answer
    (success, partial, infeasible, blocked) and is what drives `succeeded` when present.
    Everything is passed through verbatim so no failure is papered over.

    When the run requested an answer schema, the validated answer lands in `data` as a
    JSON-mode dump and `answer` stays None. A run that settles idle without producing an
    answer can leave `data` None even when `succeeded` is True.
    """

    succeeded: bool
    status: str
    outcome: str | None = None
    answer: str | None = None
    data: dict | None = None
    error: str | None = None
    session_id: str | None = None
    agent_view_url: str | None = None
