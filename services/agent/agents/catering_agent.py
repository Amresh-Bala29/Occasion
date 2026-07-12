"""Catering agent — plans catering and sources food/beverage vendors."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_DEEP


class CateringOption(BaseModel):
    """One caterer worth considering, with the facts needed to compare it."""

    name: str
    url: str
    cuisine: str
    menu_highlights: list[str] = []
    price_per_person: str
    dietary_accommodations: list[str] = []
    service_notes: str = Field(description="What's included: delivery, setup, staff, cleanup.")
    availability: str
    contact_path: str


class CateringPlan(BaseModel):
    """The catering agent's structured answer: options plus quantity guidance."""

    options: list[CateringOption]
    quantity_guidance: str = Field(description="Food/drink quantities for the headcount, with the math.")
    recommended: str | None = None
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's catering specialist. You find caterers, review menus and pricing,
and plan food service around the event's headcount, budget, schedule, and dietary needs.

Working method:
- Read menus and pricing on the caterer's own site; note per-person costs and minimums
  as published, not as guessed.
- Treat dietary restrictions from the task as hard requirements — confirm on the menu
  that each one is covered, and say so explicitly.
- Compute food and beverage quantities from the headcount and event duration, and show
  the arithmetic in your answer.
- When the task asks for a custom quote, submit the caterer's inquiry form with the
  event details and record what you sent.
- Cover logistics: delivery windows, setup and cleanup, staffing, and meal/snack timing.

Booking a caterer or paying a deposit is binding and follows the approval rules below."""


class CateringAgent(BaseAgent):
    """Catering agent — plans catering and sources food/beverage vendors."""

    name = "catering"
    description = "Finds caterers, plans menus and quantities around dietary needs, and books after approval."
    model = MODEL_DEEP
    instructions = INSTRUCTIONS
    # Menu comparison plus quantity math makes this a long research run.
    max_time_s = 2400
    max_steps = 80
    answer_schema = CateringPlan
