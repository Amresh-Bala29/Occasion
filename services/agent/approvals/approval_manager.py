"""Coordinates human-in-the-loop approvals.

The trigger the rest of the system was missing: when an agent proposes a
sensitive or over-limit action, `ApprovalManager.review` decides — using the
event's spending limit and rules — whether it may proceed. When it may not, it
writes a real `Approval` row through the repository so the existing dashboard and
resolve endpoint pick it up. Actions that fall within the user's auto-approve
rules pass through with no row written.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from approvals import sensitive_actions, spending_rules
from approvals.sensitive_actions import ActionCategory
from approvals.spending_rules import Outcome, SpendingPolicy

if TYPE_CHECKING:
    from database.repositories.event_repository import EventRepository


@dataclass
class ProposedAction:
    event_id: str
    agent: str  # display name as it should appear on the row, e.g. "Purchasing agent"
    category: ActionCategory
    title: str
    description: str
    vendor: str
    amount_usd: float = 0.0
    thread_id: str | None = None


@dataclass
class ApprovalDecision:
    requires_approval: bool
    approval_id: str | None
    reason: str


class ApprovalManager:
    def __init__(self, repo: EventRepository) -> None:
        self._repo = repo

    def review(self, action: ProposedAction) -> ApprovalDecision:
        policy = self._policy_for_event(action.event_id)
        decision = policy.evaluate(action.category, action.amount_usd)

        if decision.outcome is Outcome.AUTO_APPROVED:
            return ApprovalDecision(requires_approval=False, approval_id=None, reason=decision.reason)

        kind, tag, tone = sensitive_actions.display_fields(action.category, decision.over_limit)
        row = self._repo.create_approval(
            event_id=action.event_id,
            kind=kind,
            agent=action.agent,
            agent_tone=tone,
            tag=tag,
            title=action.title,
            description=action.description or decision.reason,
            amount=spending_rules.format_usd(action.amount_usd),
            vendor=action.vendor,
            thread_id=action.thread_id,
        )
        return ApprovalDecision(requires_approval=True, approval_id=row.id, reason=decision.reason)

    def _policy_for_event(self, event_id: str) -> SpendingPolicy:
        limit = spending_rules.parse_amount(self._repo.get_auto_approve_limit(event_id))
        rule_values = {rule.label: rule.value for rule in self._repo.get_spending_rules(event_id)}
        return SpendingPolicy(limit, rule_values)
