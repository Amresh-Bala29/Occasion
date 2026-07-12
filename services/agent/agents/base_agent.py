"""Base agent — shared interface and lifecycle for all domain agents."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from core.config import settings
from core.security import domain_guardrail
from integrations.h_company.client import HClient
from integrations.h_company.schemas import MODEL_DEEP, SessionResult
from integrations.h_company.session import inline_web_agent
from models.task import Task

# Appended to every domain agent's instructions. Mirrors the product's approval gates
# (objective 13; blocked actions live in core.config): agents research and prepare on their
# own, but sensitive commitments need explicit authorization in the task text itself.
GUARDRAILS = """\
Operating rules, in addition to your task:
- Never submit a payment, sign a contract, or place a binding booking or order unless the
  task text explicitly states that approval was granted for that exact action.
- Respect any budget cap stated in the task; stop and report instead of exceeding it.
- If a login, CAPTCHA, or two-factor prompt blocks you, stop and report the blocker as
  your outcome rather than guessing credentials or working around it.
- Never enter credentials, personal data, or payment details beyond what the task
  explicitly provides.
- Back every claim in your answer with the URL of the page where you verified it."""


class BaseAgent:
    """Common surface every domain agent implements.

    Subclasses declare their H deployment as class attributes — model, instructions,
    browser start page, run bounds, answer schema, skills — and inherit `run`, which
    executes one task as an H computer-use session and returns an honest SessionResult.
    """

    name: str = "base"
    description: str = ""
    model: str = MODEL_DEEP
    instructions: str = ""
    start_url: str | None = None
    max_steps: int | None = None
    max_time_s: float | None = None
    answer_schema: type[BaseModel] | None = None
    skills: list[dict[str, str]] | None = None

    def __init__(self, context: Any | None = None, client: HClient | None = None) -> None:
        self.context = context
        self._client = client

    def agent_spec(self) -> dict[str, object]:
        """This agent's inline H definition, sent with every session."""
        parts = [self.instructions, GUARDRAILS, domain_guardrail()]
        return inline_web_agent(
            name=f"occasion-{self.name}",
            description=self.description,
            model=self.model,
            instructions="\n\n".join(part for part in parts if part),
            start_url=self.start_url,
            skills=self.skills,
        )

    def build_prompt(self, task: str | Task) -> str:
        """The session's user message; plain strings pass through untouched."""
        if isinstance(task, Task):
            # Event ids are human-readable slugs, so they add real context to the run.
            return f"{task.title} (event: {task.event_id})"
        return task

    async def run(self, task: str | Task) -> SessionResult:
        """Run one task as a computer-use session on H.

        The SDK call blocks until the session settles, so it runs in a worker thread to
        keep the caller's event loop free. Failures come back as results, never raised.
        """
        if not settings.hai_api_key:
            return SessionResult(
                succeeded=False,
                status="error",
                error="HAI_API_KEY is not configured; set it in services/agent/.env",
            )
        client = self._client or HClient.from_settings()
        return await asyncio.to_thread(
            client.run_task,
            self.build_prompt(task),
            self.agent_spec(),
            answer_schema=self.answer_schema,
            max_steps=self.max_steps,
            max_time_s=self.max_time_s,
            group_id=self._group_id(task),
        )

    def _group_id(self, task: str | Task) -> str | None:
        # Groups an event's sessions together in H's console.
        return task.event_id if isinstance(task, Task) else None
