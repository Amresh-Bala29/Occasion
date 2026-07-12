"""Scheduling agent — builds and maintains the event schedule."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_FAST


class CalendarEntry(BaseModel):
    """One calendar event this run created, updated, or failed to place."""

    title: str
    start: str
    end: str
    status: str = Field(description="created | updated | failed, with the reason in notes.")
    link: str | None = Field(None, description="The calendar event's URL.")
    notes: str | None = None


class ScheduleReport(BaseModel):
    """The scheduling agent's structured answer: what landed on the calendar."""

    entries: list[CalendarEntry]
    conflicts: list[str] = Field(default=[], description="Requested slots that collided with existing events.")
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's scheduling specialist. You manage the event's calendar: vendor calls,
venue tours, payment deadlines, delivery windows, staff shifts, setup, rehearsals,
catering arrivals, event sessions, and cleanup.

Working method:
- Work in the signed-in Google Calendar; every entry gets an unambiguous title, the
  exact times and timezone from the task, and the location or call link when given.
- Check the target slot for collisions before creating an entry; report conflicts
  instead of double-booking.
- For updates, find the existing entry by title and date and modify it — don't create
  duplicates.
- Copy each saved entry's link as evidence that it exists.

Calendar entries are reversible, so proceed without extra confirmation — but never
delete entries the task didn't ask you to touch."""


class SchedulingAgent(BaseAgent):
    """Scheduling agent — builds and maintains the event schedule."""

    name = "scheduling"
    description = "Creates and maintains calendar entries for every event deadline, shift, and session."
    model = MODEL_FAST
    instructions = INSTRUCTIONS
    # Calendar UIs are fast repetitive flows; compact confirmations fit FAST's 4K cap.
    start_url = "https://calendar.google.com"
    max_time_s = 900
    max_steps = 40
    answer_schema = ScheduleReport
