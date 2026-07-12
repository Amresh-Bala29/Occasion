"""Registry of actions that always require approval.

The five action categories map one-to-one onto the spending rules the user
controls in the UI (see `spending_rules` seed data). Each category carries the
policy that governs it: which spending rule labels it, whether its auto path is
gated on the amount, and whether it is an irreversible commitment that needs
sign-off even when the matching rule is set to Auto. The category also owns its
display defaults (`kind`, `tag`, `tone`) so the approval row reads the same way
the seeded demo rows do.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActionCategory(str, Enum):
    PURCHASE = "purchase"
    DEPOSIT = "deposit"
    EMAIL = "email"
    CONTRACT = "contract"
    PRIVATE_DATA = "private_data"


@dataclass(frozen=True)
class CategoryPolicy:
    # `rule_label` matches a SpendingRule.label so the user's Auto/Ask-first toggle applies.
    rule_label: str
    # Amount-gated categories auto-approve only while the spend stays under the limit.
    amount_gated: bool
    # Irreversible commitments always need sign-off, even when their rule reads Auto.
    irreversible_floor: bool
    kind: str
    tag: str
    tone: str


_POLICIES: dict[ActionCategory, CategoryPolicy] = {
    ActionCategory.PURCHASE: CategoryPolicy(
        rule_label="Purchases under the limit",
        amount_gated=True,
        irreversible_floor=False,
        kind="Purchase",
        tag="Purchase",
        tone="green",
    ),
    ActionCategory.DEPOSIT: CategoryPolicy(
        rule_label="Deposits & payments",
        amount_gated=True,
        irreversible_floor=False,
        kind="Booking",
        tag="Deposit",
        tone="green",
    ),
    ActionCategory.EMAIL: CategoryPolicy(
        rule_label="Sending emails",
        amount_gated=False,
        irreversible_floor=False,
        kind="Email",
        tag="Outbound email",
        tone="blue",
    ),
    ActionCategory.CONTRACT: CategoryPolicy(
        rule_label="Vendor contracts",
        amount_gated=False,
        irreversible_floor=True,
        kind="Contract",
        tag="Binding contract",
        tone="green",
    ),
    ActionCategory.PRIVATE_DATA: CategoryPolicy(
        rule_label="Sharing private data",
        amount_gated=False,
        irreversible_floor=True,
        kind="Data",
        tag="Private data",
        tone="amber",
    ),
}


def policy_for(category: ActionCategory) -> CategoryPolicy:
    return _POLICIES[category]


def display_fields(category: ActionCategory, over_limit: bool) -> tuple[str, str, str]:
    """The (kind, tag, tone) an approval row should show for this category.

    Over-limit spends surface as an amber "Over limit" flag, matching the seeded
    purchasing-agent approval; everything else keeps the category's defaults.
    """
    policy = policy_for(category)
    if over_limit:
        return policy.kind, "Over limit", "amber"
    return policy.kind, policy.tag, policy.tone
