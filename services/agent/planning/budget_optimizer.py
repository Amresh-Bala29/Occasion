"""Budget allocation and optimization.

Reconciles the plan's budget — the budget agent's line-by-line review when there is one,
otherwise the synthesis allocations — into the integer category rows and headline totals
the dashboard reads, and reports how far commitments run over the stated cap so the risk
analyzer can flag it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from database import models as orm

if TYPE_CHECKING:
    from agents.budget_agent import BudgetReview
    from planning.constraints import PlanningConstraints
    from workflows.event_planning import EventPlan

_DOLLARS = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)")
_MINUS = "−"  # the seed formats savings with a Unicode minus, not a hyphen


@dataclass
class BudgetPlan:
    """The persistable budget: per-category rows, savings, and the event's headline totals."""

    categories: list[orm.BudgetCategory]
    savings: list[orm.SavingSuggestion]
    total_usd: int
    paid_usd: int
    pending_usd: int
    footnote: str
    over_budget_usd: float


class BudgetOptimizer:
    def __init__(
        self,
        plan: EventPlan,
        *,
        constraints: PlanningConstraints,
        review: BudgetReview | None = None,
    ) -> None:
        self._plan = plan
        self._constraints = constraints
        self._review = review

    def build(self, event_id: str) -> BudgetPlan:
        categories = self._categories(event_id)
        committed = sum(category.committed_usd for category in categories)
        paid = sum(category.paid_usd for category in categories)
        over = self._constraints.over_budget_by(committed)
        return BudgetPlan(
            categories=categories,
            savings=self._savings(event_id),
            total_usd=self._total(committed),
            paid_usd=paid,
            pending_usd=committed - paid,
            footnote=self._footnote(committed, over),
            over_budget_usd=over,
        )

    def _categories(self, event_id: str) -> list[orm.BudgetCategory]:
        tallies = self._from_review() if (self._review is not None and self._review.lines) else self._from_allocations()
        # Largest commitments first, matching the dashboard's ordering.
        ordered = sorted(tallies, key=lambda tally: tally[1], reverse=True)
        return [
            orm.BudgetCategory(
                event_id=event_id, name=name, committed_usd=committed, paid_usd=paid, estimate=estimate, ordinal=ordinal
            )
            for ordinal, (name, committed, paid, estimate) in enumerate(ordered)
        ]

    def _from_allocations(self) -> list[tuple[str, int, int, bool | None]]:
        # Synthesis allocations are all estimates: nothing is confirmed or paid yet.
        return [(alloc.category, round(alloc.estimated_usd), 0, True) for alloc in self._plan.budget]

    def _from_review(self) -> list[tuple[str, int, int, bool | None]]:
        committed: dict[str, float] = {}
        paid: dict[str, float] = {}
        confirmed_seen: dict[str, bool] = {}
        order: list[str] = []
        for line in self._review.lines:
            if line.category not in committed:
                committed[line.category] = 0.0
                paid[line.category] = 0.0
                confirmed_seen[line.category] = False
                order.append(line.category)
            committed[line.category] += line.confirmed_usd if line.confirmed_usd is not None else (line.estimated_usd or 0.0)
            paid[line.category] += line.paid_usd or 0.0
            if line.confirmed_usd is not None:
                confirmed_seen[line.category] = True
        # `estimate` stays True only while a category has no confirmed figure at all (else None, so the DTO omits it).
        return [
            (name, round(committed[name]), round(paid[name]), None if confirmed_seen[name] else True) for name in order
        ]

    def _total(self, committed: int) -> int:
        # The headline total is the ceiling: the stated cap, else the plan's own total, else what's committed.
        cap = self._constraints.budget_cap_usd
        if cap is not None:
            return round(cap)
        if self._plan.total_budget_usd is not None:
            return round(self._plan.total_budget_usd)
        return committed

    def _savings(self, event_id: str) -> list[orm.SavingSuggestion]:
        if self._review is None:
            return []
        rows = []
        for ordinal, text in enumerate(self._review.savings_suggestions):
            match = _DOLLARS.search(text)
            amount = f"{_MINUS}${int(float(match.group(1).replace(',', ''))):,}" if match else ""
            rows.append(orm.SavingSuggestion(event_id=event_id, title=_headline(text), amount=amount, note=text, ordinal=ordinal))
        return rows

    def _footnote(self, committed: int, over: float) -> str:
        cap = self._constraints.budget_cap_usd
        if cap is not None:
            if over > 0:
                return f"Estimated commitments run ${over:,.0f} over the ${cap:,.0f} budget — trim before committing."
            return f"Estimated commitments keep you ${cap - committed:,.0f} under the ${cap:,.0f} budget."
        if self._review is not None and self._review.notes:
            return self._review.notes
        return ""


def _headline(text: str) -> str:
    # First sentence (trimmed) is the suggestion's title; the full text stays as the note.
    head = text.split(".")[0].strip()
    return head if len(head) <= 60 else head[:57].rstrip() + "…"
