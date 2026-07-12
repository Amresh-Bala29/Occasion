"""Tests for the guardrails: the config-sourced policy, the checks, and the prompt wiring."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the agent service root importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.venue_agent import VenueAgent  # noqa: E402
from core.security import (  # noqa: E402
    Permissions,
    domain_guardrail,
    get_permissions,
)


def test_get_permissions_reads_config_defaults() -> None:
    get_permissions.cache_clear()
    try:
        permissions = get_permissions()
    finally:
        get_permissions.cache_clear()

    assert "lu.ma" in permissions.allowed_domains
    assert "partiful.com" in permissions.allowed_domains
    assert permissions.blocked_actions == ("purchase_without_approval", "submit_payment_form")


def test_domain_checks() -> None:
    permissions = Permissions(allowed_domains=("lu.ma", "eventbrite.com", "mail.google.com"))

    assert permissions.is_domain_allowed("https://lu.ma/events/123") is True
    assert permissions.is_domain_allowed("https://www.eventbrite.com/e/456") is True  # subdomain
    assert permissions.is_domain_allowed("eventbrite.com") is True  # bare host
    assert permissions.is_domain_allowed("https://evil-lu.ma/") is False  # lookalike
    assert permissions.is_domain_allowed("https://notlu.ma/") is False
    assert permissions.is_domain_allowed("https://drive.google.com/") is False  # sibling, not sub
    assert permissions.is_domain_allowed("https://partiful.com/") is False  # not in this list
    assert permissions.is_domain_allowed("") is False


def test_action_checks() -> None:
    permissions = Permissions(blocked_actions=("purchase_without_approval",))

    assert permissions.is_action_blocked("purchase_without_approval") is True
    assert permissions.is_action_blocked("send_email") is False


def test_domain_guardrail_lists_domains() -> None:
    text = domain_guardrail(Permissions(allowed_domains=("lu.ma", "eventbrite.com")))

    assert "Signed-in account work" in text
    assert "lu.ma, eventbrite.com" in text


def test_domain_guardrail_is_empty_without_domains() -> None:
    assert domain_guardrail(Permissions()) == ""


def test_agents_carry_the_domain_guardrail() -> None:
    # Against the real repo policy: the guardrail line must actually reach the inline
    # agent definition H receives, listing the allowed signed-in surfaces.
    get_permissions.cache_clear()
    try:
        instructions = VenueAgent().agent_spec()["instructions"]
        assert "Signed-in account work" in instructions
        assert "lu.ma" in instructions
    finally:
        get_permissions.cache_clear()
