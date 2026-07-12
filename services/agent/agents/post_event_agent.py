"""Post-event agent — handles wrap-up, thank-yous, and follow-ups."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_DEEP


class FollowUpAction(BaseModel):
    """One wrap-up action and what actually happened to it."""

    kind: str = Field(description="payment | thank_you | survey | refund_request | receipt | report")
    counterparty: str = Field(description="Vendor, attendee group, or staff member concerned.")
    status: str = Field(description="done | blocked | aborted, with the reason in notes.")
    evidence_url: str | None = Field(None, description="Sent email, receipt, or confirmation page URL.")
    notes: str | None = None


class PostEventReport(BaseModel):
    """The post-event agent's structured answer: every follow-up, honestly accounted."""

    actions: list[FollowUpAction]
    outstanding: list[str] = Field(default=[], description="Wrap-up items that still need attention.")
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's post-event specialist. After the event you settle the loose ends:
final vendor payments, thank-you emails, feedback surveys, receipt collection, refund
requests, and gathering photos and video.

Working method:
- Work from the signed-in mailbox for correspondence; keep each vendor's thread intact
  by replying in-thread rather than starting new ones.
- A vendor payment or refund request may only be executed when the task text explicitly
  states approval was granted for that amount; otherwise prepare it and report status
  "aborted".
- Collect receipts and invoices as URLs or attachment names so the budget can be
  reconciled line by line.
- Thank-yous and surveys go to the groups the task names — vendors, staff, attendees —
  with the survey link included where provided.
- Report anything you could not finish under outstanding, with what's missing.

Accuracy beats speed here: money and relationships are on the line."""


class PostEventAgent(BaseAgent):
    """Post-event agent — handles wrap-up, thank-yous, and follow-ups."""

    name = "post_event"
    description = "Settles post-event payments, thank-yous, surveys, and receipts; pays only with approval."
    model = MODEL_DEEP
    instructions = INSTRUCTIONS
    # Wrap-up starts from the mailbox: threads, receipts, and follow-ups live there.
    start_url = "https://mail.google.com"
    max_time_s = 1200
    max_steps = 50
    answer_schema = PostEventReport
