"""Requirements agent — extracts and structures event requirements from the client."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.client import run_structured_completion
from integrations.h_company.schemas import MODEL_DEEP, SessionResult
from memory.event_memory import OPEN_QUESTIONS, REQUIREMENTS
from models.task import Task

if TYPE_CHECKING:
    from core.state import Memory


class EventRequirements(BaseModel):
    """Everything the interview has established so far, plus what's still open."""

    event_type: str | None = None
    date: str | None = None
    duration: str | None = None
    location: str | None = Field(default=None, description="City or neighborhood, as the client stated it.")
    venue_preferences: str | None = Field(
        default=None, description="Preferred venue type or features, e.g. 'waterfront private event space'."
    )
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
- The transcript is cumulative: re-read every turn before answering, and keep each fact
  from earlier client messages filled in — never leave a field null that the client
  answered in any turn.
- Record informally phrased dates and places as given ("Sept 18", "SoMa") instead of
  leaving them null; venue wishes ("waterfront event space") go in venue_preferences,
  not location.
- Normalize obvious formats (numbers for headcount and budget) without changing meaning.
- Capture stated priorities in the client's own words.
- Put every requirement that is still missing or ambiguous into open_questions, phrased
  as the next question to ask the client, most important first.
- Never put an already-answered requirement back into open_questions.
- An empty open_questions list means the interview has covered everything."""


# The interview asks in rounds; after this many it stops digging and calls the brief
# complete rather than let the model keep finding one more thing to ask. Each round it
# already asked shows up in the transcript as a marker line (ChatPanel.buildTranscript
# writes it), so counting those markers bounds how many rounds the client ever sees.
MAX_CLARIFYING_ROUNDS = 1
_QUESTION_ROUND_MARKER = "Occasion asked:"


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
        result = await asyncio.to_thread(
            run_structured_completion,
            self.build_prompt(task),
            self.instructions,
            EventRequirements,
            model=self.model,
            http_client=self._http,
        )
        return self._cap_clarifying_rounds(result, task)

    def _cap_clarifying_rounds(self, result: SessionResult, task: str | Task) -> SessionResult:
        """Force the brief complete once the interview has asked its limit of rounds.

        Empty open_questions is the interview's "done" signal — the intake page reads it to
        open the dashboard. The model can otherwise surface one more question every turn, so
        past MAX_CLARIFYING_ROUNDS we clear open_questions ourselves and let the fields it
        did extract stand. The round count comes off the transcript's own markers, so this is
        inert on any input that carries none (a bare workspace message never caps).
        """
        if not result.succeeded or not result.data:
            return result
        if _rounds_asked(task) < MAX_CLARIFYING_ROUNDS:
            return result
        requirements = EventRequirements.model_validate(result.data)
        if not requirements.open_questions:
            return result
        requirements.open_questions = []
        # Re-dump both representations so `answer` (raw JSON) can't disagree with `data`.
        return result.model_copy(
            update={"data": requirements.model_dump(mode="json"), "answer": requirements.model_dump_json()}
        )


def _rounds_asked(task: str | Task) -> int:
    """How many question rounds the transcript already records. ChatPanel.buildTranscript
    writes one marker line per round it asked; other inputs carry none and so count zero."""
    transcript = task.title if isinstance(task, Task) else task
    return sum(1 for line in transcript.splitlines() if line.startswith(_QUESTION_ROUND_MARKER))


def merge_requirements(prior: EventRequirements, new: EventRequirements) -> EventRequirements:
    """Backfill fields the latest extraction left empty from the prior turn's snapshot.

    Every turn re-extracts the whole transcript from scratch, so a fact answered earlier
    ("july 20th") can silently vanish from a later extraction. New non-empty values always
    win; open_questions stays per-turn — backfilling it would resurrect answered questions.
    """
    merged = new.model_copy()
    for field in EventRequirements.model_fields:
        if field == "open_questions":
            continue
        value = getattr(merged, field)
        # Explicit emptiness, not truthiness: a stated headcount=0 or budget_usd=0.0 stands.
        if value is None or value == "" or value == []:
            setattr(merged, field, getattr(prior, field))
    return merged


def remember_requirements(
    memory: Memory, requirements: EventRequirements, *, event_id: str, user_id: str | None = None
) -> None:
    """Persist a completed requirements extraction so downstream work starts from it.

    Accumulates the user's long-term preferences and snapshots the running requirements
    (and any still-open questions) into event memory. Shared by the chat loop and the
    planning workflow so the two never drift on what a requirements turn saves.
    """
    memory.preferences.accumulate(requirements, user_id=user_id)
    event_memory = memory.event(event_id)
    event_memory.set(REQUIREMENTS, requirements.model_dump(mode="json"))
    if requirements.open_questions:
        event_memory.set(OPEN_QUESTIONS, requirements.open_questions)
