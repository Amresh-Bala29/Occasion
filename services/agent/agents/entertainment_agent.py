"""Entertainment agent — books entertainment and performers."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_DEEP


class EntertainmentOption(BaseModel):
    """One act worth considering, with the facts needed to compare it."""

    act_name: str
    act_type: str = Field(description="DJ, band, speaker, host, comedian, photobooth, activity, ...")
    url: str
    price_notes: str
    availability: str
    technical_requirements: str = Field(description="Stage, power, AV, and space the act needs.")
    review_summary: str
    contact_path: str
    pros: list[str] = []
    cons: list[str] = []


class EntertainmentResearch(BaseModel):
    """The entertainment agent's structured answer: a compared shortlist."""

    options: list[EntertainmentOption]
    recommended: str | None = None
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's entertainment specialist. You find and evaluate DJs, musicians,
speakers, hosts, comedians, performers, photobooths, and interactive activities on
booking marketplaces and the acts' own sites.

Working method:
- Compare on price, availability for the event date, reviews, and fit with the event's
  audience and tone.
- Capture each act's technical requirements (stage, power, AV, space) — they decide
  whether the act physically fits the venue.
- Summarize reviews from what's actually on the page; quote counts and ratings rather
  than impressions.
- When the task asks for outreach, send the act's booking inquiry with the event
  details and record what you sent.

Booking an act or paying a deposit is binding and follows the approval rules below."""


class EntertainmentAgent(BaseAgent):
    """Entertainment agent — books entertainment and performers."""

    name = "entertainment"
    description = "Finds and compares performers and activities, checks technical fit, and books after approval."
    model = MODEL_DEEP
    instructions = INSTRUCTIONS
    # Review-weighing across marketplaces is research-tier work.
    max_time_s = 2400
    max_steps = 80
    answer_schema = EntertainmentResearch
