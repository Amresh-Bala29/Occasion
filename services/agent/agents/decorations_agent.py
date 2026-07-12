"""Decorations agent — plans and sources decorations."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_DEEP


class SupplyItem(BaseModel):
    """One decoration or supply pick, ready for a purchase decision."""

    item: str
    vendor: str
    url: str
    unit_price: str
    quantity: int
    shipping_notes: str = Field(description="Delivery estimate and cost to the event location.")
    notes: str | None = None


class SupplyShortlist(BaseModel):
    """The decorations agent's structured answer: an itemized, priced shortlist."""

    items: list[SupplyItem]
    estimated_total: str
    cart_url: str | None = Field(None, description="Saved cart or list URL, when the store supports one.")
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's decorations and supplies specialist. You source signage, banners,
linens, lighting, name tags, furniture, stage equipment, registration supplies, gifts,
prizes, and cleaning materials from online stores.

Working method:
- Match items to the event's branding, headcount, and venue; size quantities from the
  task's numbers and say how you counted.
- Record exact product URLs, unit prices, and shipping estimates to the event location;
  the shipping deadline disqualifies items that arrive late.
- Prefer stores already in use for the event where the task names them; otherwise
  compare a couple of options per item on price and delivery.
- You may assemble carts or saved lists as evidence, but checkout belongs to the
  purchasing agent — never enter a payment flow.

Your output is a decision-ready shortlist, not a completed purchase."""


class DecorationsAgent(BaseAgent):
    """Decorations agent — plans and sources decorations."""

    name = "decorations"
    description = "Sources decorations and supplies into an itemized, priced shortlist; never checks out."
    model = MODEL_DEEP
    instructions = INSTRUCTIONS
    # Comparison shopping with itemized output; checkout is the purchasing agent's job.
    max_time_s = 1200
    max_steps = 50
    answer_schema = SupplyShortlist
