"""Purchasing agent — executes purchases and manages orders."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_DEEP


class OrderAttempt(BaseModel):
    """What happened to one purchase: placed, blocked, or deliberately aborted."""

    item: str
    vendor: str
    url: str
    amount: str
    status: str = Field(description="placed | blocked | aborted, with the deciding reason in notes.")
    confirmation_url: str | None = Field(None, description="Order confirmation page or receipt URL.")
    tradeoff_statement: str = Field(
        description="The tradeoff weighed before acting: budget, deadline, quality, cancellation policy."
    )
    notes: str | None = None


class PurchaseReport(BaseModel):
    """The purchasing agent's structured answer: every attempt, honestly accounted."""

    orders: list[OrderAttempt]
    total_spent: str
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's purchasing specialist — the only agent that completes checkouts. You
execute purchase tasks prepared by the other agents and manage the resulting orders.

Working method:
- A purchase may only proceed when the task text explicitly states approval was granted
  for that exact item and amount. No approval statement in the task means research the
  checkout up to the payment step, then stop and report status "aborted".
- Before paying, state the tradeoff you weighed: price against budget cap, shipping
  against the event deadline, quality and reviews against cost, cancellation and refund
  policy, and any backup supplier. Put it in the order's tradeoff_statement.
- Prefer options with bulk discounts or free shipping when they beat the current pick
  at equal quality; say so rather than silently switching.
- Capture the confirmation page URL and order number for every placed order; a purchase
  without evidence is not placed.
- Use only payment methods already available in the signed-in browser session; never
  type card numbers or account credentials.

Stay strictly within the amounts the task authorizes."""


class PurchasingAgent(BaseAgent):
    """Purchasing agent — executes purchases and manages orders."""

    name = "purchasing"
    description = "Executes approved purchases through real checkouts, stating tradeoffs and keeping receipts."
    model = MODEL_DEEP
    instructions = INSTRUCTIONS
    # Checkout flows are short; a purchase run that wanders is a bad sign.
    max_time_s = 1200
    max_steps = 50
    answer_schema = PurchaseReport
