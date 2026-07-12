"""Risk analysis for the event plan.

Collapses each plan risk's likelihood and impact into the single Low/Medium/High level
the dashboard shows, and adds the risks that only fall out of the numbers — commitments
over the budget cap, a timeline too short to source what's left, or a figure the budget
agent flagged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from database import models as orm

if TYPE_CHECKING:
    from datetime import date

    from agents.budget_agent import BudgetReview
    from planning.constraints import PlanningConstraints
    from workflows.event_planning import EventPlan

# A tight timeline only counts as a risk this close to the event, with sourcing still open.
_TIGHT_TIMELINE_DAYS = 21

_RANK = {"high": 3, "medium": 2, "moderate": 2, "low": 1}
_LEVEL_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def _rank(text: str) -> int:
    lowered = text.strip().lower()
    for word, value in _RANK.items():
        if word in lowered:
            return value
    return 2  # unlabeled likelihood/impact sits in the middle rather than vanishing


def _level(likelihood: str, impact: str) -> str:
    score = _rank(likelihood) * _rank(impact)
    if score >= 6:
        return "High"
    if score >= 3:
        return "Medium"
    return "Low"


class RiskAnalyzer:
    """Turns the plan's risks (plus derived ones) into dashboard risk rows, worst first."""

    def __init__(
        self,
        plan: EventPlan,
        *,
        constraints: PlanningConstraints,
        today: date,
        over_budget_usd: float = 0.0,
        budget_review: BudgetReview | None = None,
    ) -> None:
        self._plan = plan
        self._constraints = constraints
        self._today = today
        self._over_budget_usd = over_budget_usd
        self._review = budget_review

    def rows(self, event_id: str) -> list[orm.RiskItem]:
        found: list[tuple[str, str, str]] = [
            (_level(risk.likelihood, risk.impact), risk.risk, risk.mitigation) for risk in self._plan.risks
        ]
        found.extend(self._derived())
        found.sort(key=lambda item: _LEVEL_ORDER.get(item[0], 1))  # High first; stable within a level
        return [
            orm.RiskItem(event_id=event_id, level=level, title=title, mitigation=mitigation, ordinal=ordinal)
            for ordinal, (level, title, mitigation) in enumerate(found)
        ]

    def _derived(self) -> list[tuple[str, str, str]]:
        derived: list[tuple[str, str, str]] = []

        if self._over_budget_usd > 0:
            derived.append(
                (
                    "High",
                    f"Budget over plan by ${self._over_budget_usd:,.0f}",
                    "Commitments exceed the stated budget; trim discretionary lines or raise the cap before booking.",
                )
            )

        days = self._constraints.days_to_event(self._today)
        if days is not None and 0 <= days < _TIGHT_TIMELINE_DAYS and self._plan.vendor_categories:
            derived.append(
                (
                    "Medium",
                    "Timeline is tight",
                    f"{days} days out with {len(self._plan.vendor_categories)} categories still to source; "
                    "prioritize the longest-lead bookings first.",
                )
            )

        if self._review is not None:
            for flag in self._review.risks:
                derived.append(("Medium", flag, "Flagged by the budget agent — verify the figure at its source."))

        return derived
