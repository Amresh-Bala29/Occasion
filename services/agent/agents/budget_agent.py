"""Budget agent — tracks and optimizes the event budget."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_DEEP


class BudgetLine(BaseModel):
    """One budget line, tracked from estimate to money out the door."""

    category: str
    vendor: str | None = None
    estimated_usd: float | None = None
    confirmed_usd: float | None = None
    paid_usd: float | None = None
    refund_policy_notes: str | None = None
    source_url: str | None = Field(None, description="Where the figure was verified.")


class BudgetReview(BaseModel):
    """The budget agent's structured answer: the live picture plus where it's heading."""

    lines: list[BudgetLine]
    remaining_budget_usd: float | None = None
    risks: list[str] = Field(default=[], description="Lines trending over, unverified figures, missed deposits.")
    savings_suggestions: list[str] = []
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's budget specialist. You keep the live budget honest: estimated versus
confirmed versus paid, deposits and refund policies, unexpected expenses, and where money
can be saved.

Working method:
- Verify figures at their source — vendor pages, quotes, order confirmations — and record
  the URL for each number you assert.
- Distinguish estimated, confirmed (quoted or contracted), and paid amounts; never let an
  estimate masquerade as a commitment.
- Read cancellation and refund policies on the vendor's page and note the deadline that
  makes each deposit recoverable or not.
- Flag lines that trend over their estimate, and suggest concrete savings (alternative
  vendors, bulk pricing, dropped extras) with the evidence for each.

You report and recommend; moving money is the purchasing and post-event agents' job."""


class BudgetAgent(BaseAgent):
    """Budget agent — tracks and optimizes the event budget."""

    name = "budget"
    description = "Verifies budget figures at their sources, tracks estimates versus paid, and flags risks."
    model = MODEL_DEEP
    instructions = INSTRUCTIONS
    # Verification browsing is targeted: check figures, read policies, get out.
    max_time_s = 1200
    max_steps = 50
    answer_schema = BudgetReview
