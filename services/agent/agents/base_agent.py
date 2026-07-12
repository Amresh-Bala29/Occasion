"""Base agent — shared interface and lifecycle for all domain agents."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from core.config import settings
from core.security import domain_guardrail
from core.state import Memory
from integrations.h_company.client import HClient
from integrations.h_company.schemas import MODEL_DEEP, SessionResult
from integrations.h_company.session import inline_web_agent
from models.task import Task

logger = logging.getLogger(__name__)

# Introduces the stored project context appended to event-scoped session prompts.
CONTEXT_HEADER = "What Occasion already knows about this event:"


def with_project_context(prompt: str, memory: Any, task: Task) -> str:
    """`prompt` with the event's stored context appended, drawn through `memory`.

    This is how a session learns what the project has already established — the brief,
    the plan, decisions, preferences, and relevant notes. Reads happen on the event
    loop, before the H thread hop (core/state.py's thread rule). Degrades to the bare
    prompt when no Memory handle was injected or the read fails: missing context must
    never fail a run that could otherwise proceed.
    """
    if not isinstance(memory, Memory):
        return prompt
    try:
        context = memory.prompt_context(task.event_id, task.title, user_id=task.user_id)
    except Exception:
        logger.exception("skipping project context for event %s", task.event_id)
        return prompt
    if not context:
        return prompt
    return f"{prompt}\n\n{CONTEXT_HEADER}\n{context}"


# Appended to every domain agent's instructions. Mirrors the product's approval gates
# (objective 13; blocked actions live in core.config): agents research and prepare on their
# own, but sensitive commitments need explicit authorization in the task text itself.
# Routine web obstacles (cookie walls, popups) are the agent's own job to clear; only
# true blockers — security checks and logins the task gave no credentials for — stop it.
GUARDRAILS = """\
Operating rules, in addition to your task:
- Never submit a payment, sign a contract, or place a binding booking or order unless the
  task text explicitly states that approval was granted for that exact action.
- Respect any budget cap stated in the task; stop and report instead of exceeding it.
- Cookie banners, consent walls, newsletter popups, and similar overlays are routine,
  not blockers: dismiss them yourself and keep going.
- Stop and report only on true blockers: a login the task gave you no credentials for,
  a CAPTCHA, or a two-factor prompt. Report the blocker as your outcome — name the
  site, the page URL, and what a human must do next — rather than guessing credentials
  or working around a security check.
- In your final answer, briefly note the obstacles you cleared along the way (e.g.
  "dismissed cookie wall on eventbrite.com") so your work is auditable.
- Never enter credentials, personal data, or payment details beyond what the task
  explicitly provides.
- Back every claim in your answer with the URL of the page where you verified it."""


# Attached ahead of every browser agent's own skills: the messy real web — cookie walls,
# popups, endless lists — is routine work, not a blocker. Site-agnostic on purpose:
# url_pattern is omitted (the SDK marks it optional) so H may load these anywhere, and
# each description is the "use when…" trigger H reads to decide on loading. Shape
# mirrors the distribution agent's platform skills.
SURVIVAL_SKILLS: list[dict[str, str]] = [
    {
        "name": "dismiss-cookie-consent-walls",
        "description": (
            "Use when a cookie, consent, GDPR, or privacy banner covers the page or "
            "intercepts clicks."
        ),
        "body": (
            "1. Prefer the choice that ends the interruption fastest without an account: "
            "'Reject all', 'Necessary only', or 'Decline'; otherwise 'Accept all' — the "
            "cookie choice never affects your task.\n"
            "2. Look for the button inside the banner first, then an X in its corner.\n"
            "3. If the banner returns after navigation, dismiss it again once; if it still "
            "blocks the page, reload once and re-dismiss.\n"
            "4. Never type an email address or sign up to make a banner go away.\n"
            "5. Resume the task immediately and note 'dismissed cookie wall on <site>' for "
            "your final answer."
        ),
    },
    {
        "name": "close-popups-and-overlays",
        "description": (
            "Use when a modal, newsletter signup, discount offer, app-install banner, "
            "survey, or chat widget blocks the content you need."
        ),
        "body": (
            "1. Close it with its X, 'No thanks', 'Maybe later', 'Skip', or 'Continue to "
            "site' control; check the top corners for a small or low-contrast X.\n"
            "2. If there is no visible close control, press Escape, then try clicking the "
            "dimmed backdrop outside the dialog.\n"
            "3. Never enter an email, phone number, or credentials to close an overlay.\n"
            "4. If the same overlay reopens while you scroll, close it again and keep "
            "working — reopening popups are noise, not blockers.\n"
            "5. Resume the task and note 'closed popup on <site>' for your final answer."
        ),
    },
    {
        "name": "drain-infinite-scroll-lists",
        "description": (
            "Use when results live in an infinite-scroll list, behind 'Load more' / "
            "'Show more' buttons, or load lazily as you scroll."
        ),
        "body": (
            "1. Scroll to the bottom of the list and pause for lazy content; click 'Load "
            "more' or 'Show more' whenever it appears.\n"
            "2. Repeat until you have enough items for the task, or the list stops growing "
            "after two consecutive attempts.\n"
            "3. Keep a rough count of items seen and state it in your notes (e.g. "
            "'scrolled through 24 results').\n"
            "4. Do not scroll forever: once the task's needs are met (or ~50 items), stop "
            "and work with what is loaded.\n"
            "5. Extract items as you go — lazy lists can unload earlier content."
        ),
    },
]


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
            # Every browser agent survives the messy web; domain skills stay per-agent.
            skills=[*SURVIVAL_SKILLS, *(self.skills or [])],
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
        prompt = self.build_prompt(task)
        if isinstance(task, Task):
            # Event-scoped runs carry the project's stored context; the requirements
            # agent bypasses this (its own run sends the raw transcript) by design.
            prompt = with_project_context(prompt, self.context, task)
        client = self._client or HClient.from_settings()
        return await asyncio.to_thread(
            client.run_task,
            prompt,
            self.agent_spec(),
            answer_schema=self.answer_schema,
            max_steps=self.max_steps,
            max_time_s=self.max_time_s,
            group_id=self._group_id(task),
        )

    def _group_id(self, task: str | Task) -> str | None:
        # Groups an event's sessions together in H's console.
        return task.event_id if isinstance(task, Task) else None
