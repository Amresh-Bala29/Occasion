"""Browser configuration for H computer-use sessions.

Builds the per-run `overrides` that point the managed web agent (h/web-surfer-flash) at a
real Chrome browser — where it runs, what it opens, and whether it reuses a signed-in
profile. This is how H drives Gmail, Calendar, Luma, and the rest directly, so a logged-in
browser session stands in for per-service API keys. Overrides are the mechanism the SDK
documents for reconfiguring a registered agent's environment on a single run.
"""

from __future__ import annotations

from core.config import settings

# Dotted-path selector for the web agent's browser environment; the SDK keys per-run
# overrides as "agent.environments[kind=web].<field>".
_WEB = "agent.environments[kind=web]"


def browser_overrides() -> dict[str, object]:
    """Per-run overrides that put H in a cloud Chrome opened at Google.

    Driven entirely by settings, so the browser can be retargeted (host, start URL, headless,
    profile reuse) from the environment without touching code.
    """
    overrides: dict[str, object] = {
        f"{_WEB}.host": settings.hai_browser_host,
        f"{_WEB}.start_url": settings.hai_browser_start_url,
        f"{_WEB}.headless": settings.hai_browser_headless,
    }
    # Reuse a default browser profile so Google/Luma/etc. logins persist across runs.
    if settings.hai_browser_persist_login:
        overrides[f"{_WEB}.use_default_browser_profile"] = True
        overrides[f"{_WEB}.persist_browser_profile"] = True
    return overrides
