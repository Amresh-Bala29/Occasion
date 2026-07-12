"""Merchandise agent — designs and sources event merchandise."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_DEEP


class MerchandiseQuote(BaseModel):
    """One manufacturer's offer for a custom-branded product."""

    vendor: str
    url: str
    product: str
    material_options: list[str] = []
    unit_price_notes: str = Field(description="Price per unit at the quoted quantity, plus setup fees.")
    minimum_quantity: str
    production_time: str
    shipping_time: str
    expedite_options: str | None = None
    artwork_requirements: str = Field(description="File format, resolution, and how artwork is uploaded.")
    contact_path: str


class MerchandiseResearch(BaseModel):
    """The merchandise agent's structured answer: quotes measured against the deadline."""

    quotes: list[MerchandiseQuote]
    deadline_assessment: str = Field(description="Which quotes arrive before the event, given production plus shipping.")
    recommended: str | None = None
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's merchandise specialist. Starting from the event's logo and branding,
you find manufacturers for custom products (shirts, stickers, banners, swag), collect
quotes, and weigh production and shipping times against the event deadline.

Working method:
- Use each vendor's own quote calculator or product page for pricing; record quantity
  breaks and setup fees as published.
- Capture artwork requirements exactly (format, resolution, color space, upload path);
  upload the provided artwork only where the task supplies it and the flow requires it.
- Production time plus shipping time versus the event date is the deciding math — show
  it per quote, including expedited options and their cost.
- Flag quotes that cannot arrive on time instead of hiding them.

Placing an order or paying for a run (expedited or not) is binding and follows the
approval rules below."""


class MerchandiseAgent(BaseAgent):
    """Merchandise agent — designs and sources event merchandise."""

    name = "merchandise"
    description = "Gets custom-merch quotes, handles artwork requirements, and weighs production versus deadlines."
    model = MODEL_DEEP
    instructions = INSTRUCTIONS
    # Quote calculators and artwork-upload flows make long runs.
    max_time_s = 2400
    max_steps = 80
    answer_schema = MerchandiseResearch
