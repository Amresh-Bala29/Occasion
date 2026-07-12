"""Spending thresholds and auto-approval rules.

Turns an event's auto-approve limit and per-category Auto/Ask-first rules into a
single decision: may an agent act on its own, or does this need the user's
sign-off? This is the one place the gate logic lives — `SpendingPolicy.evaluate`
reads the category's `CategoryPolicy` and applies the user's rules on top.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from approvals import sensitive_actions
from approvals.sensitive_actions import ActionCategory

# Absent rule falls back to the strict side, so an unconfigured category still pauses.
_DEFAULT_RULE = "Ask first"


def parse_amount(value: str | float | int | None) -> float:
    """Read a display amount like "$2,940" into a number; blank or None is 0."""
    digits = re.sub(r"[^\d.]", "", str(value or ""))
    return float(digits) if digits else 0.0


class Outcome(str, Enum):
    AUTO_APPROVED = "auto_approved"
    REQUIRES_APPROVAL = "requires_approval"


@dataclass
class Decision:
    outcome: Outcome
    reason: str
    over_limit: bool = False


class SpendingPolicy:
    def __init__(self, auto_approve_limit_usd: float, rule_values: dict[str, str]) -> None:
        self._limit = auto_approve_limit_usd
        self._rule_values = rule_values

    def evaluate(self, category: ActionCategory, amount_usd: float) -> Decision:
        policy = sensitive_actions.policy_for(category)
        rule = self._rule_values.get(policy.rule_label, _DEFAULT_RULE)

        if policy.irreversible_floor:
            return Decision(Outcome.REQUIRES_APPROVAL, f"{policy.kind} always needs your sign-off")

        if rule != "Auto":
            return Decision(
                Outcome.REQUIRES_APPROVAL, f"Your rule for '{policy.rule_label}' is set to {rule}"
            )

        if policy.amount_gated and amount_usd > self._limit:
            return Decision(
                Outcome.REQUIRES_APPROVAL,
                f"{format_usd(amount_usd)} exceeds your {format_usd(self._limit)} auto-approve limit",
                over_limit=True,
            )

        return Decision(Outcome.AUTO_APPROVED, "within your auto-approve rules")


def format_usd(amount_usd: float) -> str:
    """Render a number as the "$2,940" display string the rows and UI use."""
    return f"${amount_usd:,.0f}"
