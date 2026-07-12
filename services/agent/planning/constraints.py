"""Constraint definitions and validation for planning.

The hard limits a generated plan must respect — the stated budget cap and the event
date — pulled from the requirements into one small value object, so the budget, risk,
and schedule modules answer "over budget?" and "how close is the event?" the same way
instead of each re-deriving it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.requirements_agent import EventRequirements


def parse_iso_date(text: str | None) -> date | None:
    """An ISO date parsed from `text`, or None for empty, relative, or free-form values.

    Plan dates are ISO when the event date is known and otherwise T-minus offsets or
    'pending' (see PlanMilestone.date); only the first kind is a real calendar date.
    """
    if not text:
        return None
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None


@dataclass(frozen=True)
class PlanningConstraints:
    """The plan's hard limits, as far as the requirements pinned them down."""

    budget_cap_usd: float | None = None
    event_date: date | None = None

    @classmethod
    def from_requirements(cls, requirements: EventRequirements | None) -> PlanningConstraints:
        if requirements is None:
            return cls()
        return cls(
            budget_cap_usd=requirements.budget_usd,
            event_date=parse_iso_date(requirements.date),
        )

    def over_budget_by(self, committed_usd: float) -> float:
        """Dollars `committed_usd` exceeds the stated cap by; 0 when within cap or capless."""
        if self.budget_cap_usd is None:
            return 0.0
        return max(0.0, committed_usd - self.budget_cap_usd)

    def days_to_event(self, today: date) -> int | None:
        """Whole days from `today` to the event, or None when the date isn't known."""
        if self.event_date is None:
            return None
        return (self.event_date - today).days
