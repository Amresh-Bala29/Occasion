"""Staffing agent — sources and schedules event staff."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base_agent import BaseAgent
from integrations.h_company.schemas import MODEL_DEEP


class StaffingCandidate(BaseModel):
    """One staffing option for a role: a platform listing, agency, or individual."""

    role: str
    source: str = Field(description="Platform or agency the candidate comes from.")
    url: str
    rate_notes: str
    availability: str
    contact_path: str
    notes: str | None = None


class StaffingPlan(BaseModel):
    """The staffing agent's structured answer: candidates and what's still uncovered."""

    candidates: list[StaffingCandidate]
    coverage_gaps: list[str] = Field(default=[], description="Roles or shifts with no viable candidate yet.")
    notes: str | None = None


INSTRUCTIONS = """\
You are Occasion's staffing specialist. You source temporary event staff — registration,
setup/teardown, security, bartenders, servers, technical support, photographers,
videographers, coordinators, medical personnel — across staffing platforms and agencies.

Working method:
- Match each candidate to a specific role, shift window, and arrival time from the task;
  staffing that doesn't cover the schedule is a gap, not a hire.
- Record rates exactly as listed (hourly vs flat, minimum hours) and note platform fees.
- Check ratings, reviews, or vetting badges where the platform shows them.
- When the task asks for outreach, send the platform's booking inquiry with the shift
  details and record what you sent.
- Report roles you could not cover as coverage gaps instead of stretching weak options.

Confirming a hire or paying a platform is binding and follows the approval rules below."""


class StaffingAgent(BaseAgent):
    """Staffing agent — sources and schedules event staff."""

    name = "staffing"
    description = "Sources temporary event staff across platforms and plans shift coverage; hires after approval."
    model = MODEL_DEEP
    instructions = INSTRUCTIONS
    # Multi-platform sourcing across many roles needs research-tier bounds.
    max_time_s = 2400
    max_steps = 80
    answer_schema = StaffingPlan
