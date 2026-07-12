"""Tests for the approvals trigger.

No database: the manager is driven against a fake repository that records the
approval rows it is asked to create, so the tests focus on the decision — when a
proposed action needs sign-off, and what the resulting row looks like.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from approvals.approval_manager import ApprovalManager, ProposedAction  # noqa: E402
from approvals.sensitive_actions import ActionCategory  # noqa: E402
from approvals.spending_rules import Outcome, SpendingPolicy, parse_amount  # noqa: E402
from models import web  # noqa: E402

EVENT_ID = "novaflow-summit-2026"

# The seeded rule configuration: purchases and emails auto-approve, the rest ask first.
_RULES = {
    "Purchases under the limit": "Auto",
    "Vendor contracts": "Ask first",
    "Deposits & payments": "Ask first",
    "Sending emails": "Auto",
    "Sharing private data": "Ask first",
}


class FakeRepo:
    """Stands in for EventRepository; records every approval the manager creates."""

    def __init__(self, limit: str = "$500", rules: dict[str, str] | None = None) -> None:
        self._limit = limit
        self._rules = rules if rules is not None else _RULES
        self.created: list[dict] = []

    def get_auto_approve_limit(self, event_id: str) -> str | None:
        return self._limit

    def get_spending_rules(self, event_id: str) -> list[web.SpendingRule]:
        return [
            web.SpendingRule(id=f"rule-{i}", label=label, value=value)
            for i, (label, value) in enumerate(self._rules.items())
        ]

    def create_approval(self, **fields) -> web.ApprovalItem:
        self.created.append(fields)
        return web.ApprovalItem(id=f"approval-{len(self.created)}", **fields)


def _action(category: ActionCategory, amount_usd: float = 0.0) -> ProposedAction:
    return ProposedAction(
        event_id=EVENT_ID,
        agent="Purchasing agent",
        category=category,
        title="350 × custom branded tote bags",
        description="",
        vendor="4imprint",
        amount_usd=amount_usd,
    )


# ---- parse_amount ----


def test_parse_amount_reads_display_strings() -> None:
    assert parse_amount("$2,940") == 2940.0
    assert parse_amount("$500") == 500.0
    assert parse_amount("") == 0.0
    assert parse_amount(None) == 0.0


# ---- SpendingPolicy.evaluate ----


def _policy() -> SpendingPolicy:
    return SpendingPolicy(parse_amount("$500"), _RULES)


def test_purchase_under_limit_auto_approves() -> None:
    decision = _policy().evaluate(ActionCategory.PURCHASE, 480.0)
    assert decision.outcome is Outcome.AUTO_APPROVED
    assert decision.over_limit is False


def test_purchase_over_limit_requires_approval() -> None:
    decision = _policy().evaluate(ActionCategory.PURCHASE, 2940.0)
    assert decision.outcome is Outcome.REQUIRES_APPROVAL
    assert decision.over_limit is True


def test_ask_first_rule_requires_approval_regardless_of_amount() -> None:
    decision = _policy().evaluate(ActionCategory.DEPOSIT, 50.0)
    assert decision.outcome is Outcome.REQUIRES_APPROVAL
    assert decision.over_limit is False


def test_irreversible_categories_require_approval_even_on_auto() -> None:
    policy = SpendingPolicy(parse_amount("$500"), {"Vendor contracts": "Auto", "Sharing private data": "Auto"})
    assert policy.evaluate(ActionCategory.CONTRACT, 0.0).outcome is Outcome.REQUIRES_APPROVAL
    assert policy.evaluate(ActionCategory.PRIVATE_DATA, 0.0).outcome is Outcome.REQUIRES_APPROVAL


# ---- ApprovalManager.review ----


def test_over_limit_purchase_creates_amber_over_limit_row() -> None:
    repo = FakeRepo()
    decision = ApprovalManager(repo).review(_action(ActionCategory.PURCHASE, 2940.0))

    assert decision.requires_approval is True
    assert decision.approval_id is not None
    assert len(repo.created) == 1
    row = repo.created[0]
    assert row["kind"] == "Purchase"
    assert row["tag"] == "Over limit"
    assert row["agent_tone"] == "amber"
    assert row["amount"] == "$2,940"
    # Blank description falls back to the human decision reason.
    assert "auto-approve limit" in row["description"]


def test_under_limit_purchase_writes_no_row() -> None:
    repo = FakeRepo()
    decision = ApprovalManager(repo).review(_action(ActionCategory.PURCHASE, 120.0))

    assert decision.requires_approval is False
    assert decision.approval_id is None
    assert repo.created == []
