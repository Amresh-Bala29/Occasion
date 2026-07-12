"""Venue agent — sources, evaluates, and books venues."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_DEEP


class VenueOption(BaseModel):
    """One venue worth considering, with the facts needed to compare it."""

    name: str
    url: str
    location: str
    capacity: str
    price_notes: str
    availability: str
    amenities: list[str] = []
    rules_notes: str | None = None
    contact_path: str = Field(description="How to reach the manager: form URL, email, or phone.")
    pros: list[str] = []
    cons: list[str] = []


class VenueResearch(BaseModel):
    """The venue agent's structured answer: a compared shortlist."""

    options: list[VenueOption]
    recommended: str | None = Field(None, description="Name of the best-fit option, if one stands out.")
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's venue specialist. You source venues for events end to end: search
venue marketplaces and venue websites, then evaluate each candidate against the event's
date, headcount, budget, location, equipment needs, and house rules.

Working method:
- Prefer primary sources — the venue's own site or its marketplace listing — over
  aggregator summaries.
- Verify capacity, pricing, availability, and included equipment on the page; never
  infer them.
- When the task asks for outreach, use the venue's contact form or email to request a
  quote or tour, and record exactly what you sent and where.
- Compare candidates honestly, drawbacks included; recommend a best fit but keep every
  option's facts intact so a human can decide differently.

Booking a venue is a binding commitment and follows the approval rules below."""


class VenueAgent(BaseAgent):
    """Venue agent — sources, evaluates, and books venues."""

    name = "venue"
    description = "Finds and evaluates event venues, requests quotes and tours, and books after approval."
    model = MODEL_DEEP
    instructions = INSTRUCTIONS
    # Venue sourcing is the longest-horizon research this fleet does.
    max_time_s = 2400
    max_steps = 80
    answer_schema = VenueResearch
