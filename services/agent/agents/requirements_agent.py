"""Requirements agent — extracts and structures event requirements from the client."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.client import run_structured_completion
from integrations.h_company.schemas import MODEL_DEEP, SessionResult
from models.task import Task


class EventRequirements(BaseModel):
    """Everything the interview has established so far, plus what's still open."""

    event_type: str | None = None
    date: str | None = None
    duration: str | None = None
    location: str | None = None
    headcount: int | None = None
    budget_usd: float | None = None
    food_preferences: list[str] = []
    dietary_restrictions: list[str] = []
    staffing_needs: list[str] = []
    entertainment_preferences: list[str] = []
    branding_notes: str | None = None
    accessibility_needs: list[str] = []
    shipping_deadlines: str | None = None
    priorities: list[str] = Field(default=[], description="What the client said matters most, in their words.")
    open_questions: list[str] = Field(
        default=[], description="Next questions to ask the client; empty means the interview is complete."
    )


INSTRUCTIONS = """\
You are Occasion's requirements interviewer. From a conversation transcript with the
client, you extract the event's requirements and decide what to ask next.

Rules:
- Record only what the client actually said; leave unstated fields null or empty.
- Normalize obvious formats (numbers for headcount and budget) without changing meaning.
- Capture stated priorities in the client's own words.
- Put every requirement that is still missing or ambiguous into open_questions, phrased
  as the next question to ask the client, most important first.
- An empty open_questions list means the interview has covered everything."""


class RequirementsAgent(BaseAgent):
    """Requirements agent — extracts and structures event requirements from the client."""

    name = "requirements"
    description = "Extracts structured event requirements from the client conversation and drives the interview."
    model = MODEL_DEEP
    instructions = INSTRUCTIONS
    answer_schema = EventRequirements

    def __init__(self, context: Any | None = None, http_client: httpx.Client | None = None) -> None:
        super().__init__(context)
        self._http = http_client

    async def run(self, task: str | Task) -> SessionResult:
        """Extract requirements from a transcript — a chat completion, not a browser run."""
        return await asyncio.to_thread(
            run_structured_completion,
            self.build_prompt(task),
            self.instructions,
            EventRequirements,
            model=self.model,
            http_client=self._http,
        )
