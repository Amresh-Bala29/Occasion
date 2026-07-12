"""Guardrails — the signed-in-account policy the agent runtime operates under.

Objective 19 scopes which websites the browser sessions may act on and which actions
are blocked outright. The allow-lists live in core.config; this module wraps them as
the checks and the prompt-level guardrail. The v1 consumer is prompt-level
(`domain_guardrail` rides into every agent's instructions); `blocked_actions` maps to
the approvals layer's ActionCategory gates, where hard enforcement belongs.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

from core.config import settings


@dataclass(frozen=True)
class Permissions:
    """The signed-in-account allow-list: domains the agents may act on, actions blocked outright."""

    allowed_domains: tuple[str, ...] = ()
    blocked_actions: tuple[str, ...] = ()

    def is_domain_allowed(self, url: str) -> bool:
        """True when `url`'s host is an allowed domain or a subdomain of one."""
        host = _host_of(url)
        if not host:
            return False
        return any(host == domain or host.endswith("." + domain) for domain in self.allowed_domains)

    def is_action_blocked(self, action: str) -> bool:
        return action in self.blocked_actions


@lru_cache(maxsize=1)
def get_permissions() -> Permissions:
    """The process-wide permissions, resolved once from the core.config defaults."""
    return Permissions(
        allowed_domains=settings.allowed_domains,
        blocked_actions=settings.blocked_actions,
    )


def domain_guardrail(permissions: Permissions | None = None) -> str:
    """One instruction line scoping signed-in account work to the allowed domains.

    Read as a browse allow-list the six domains would forbid the open-web vendor
    research the agents exist for, so the line scopes account-bound actions instead.
    """
    permissions = permissions if permissions is not None else get_permissions()
    if not permissions.allowed_domains:
        return ""
    domains = ", ".join(permissions.allowed_domains)
    return (
        "- Signed-in account work (posting listings, sending mail, calendar changes) is "
        f"approved only on: {domains}. Research the open web freely, but stop and report "
        "instead of logging in or submitting account-bound actions anywhere else."
    )


def _host_of(url: str) -> str | None:
    # urlparse puts a scheme-less "lu.ma" in path, not netloc; anchor it so it parses.
    return urlparse(url if "://" in url else f"//{url}").hostname
