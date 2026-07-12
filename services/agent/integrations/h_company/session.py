"""Browser configuration for H computer-use sessions.

Two ways of pointing H at a real Chrome browser, both settings-driven so the browser can
be retargeted from the environment without touching code. `browser_overrides()` builds the
per-run `overrides` that reconfigure the managed web agent (h/web-surfer-flash);
`inline_web_agent()` builds a full inline agent definition for our own domain agents,
carrying the same browser plus a per-agent model, instructions, and skills. Either way a
logged-in cloud Chrome profile stands in for per-service API keys, which is how H drives
Gmail, Calendar, Luma, and the rest directly.
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


def browser_environment(start_url: str | None = None) -> dict[str, object]:
    """The web environment for an inline agent: same browser the overrides describe.

    `start_url` lets an agent open at its canonical workplace (e.g. calendar.google.com);
    everything else follows settings.
    """
    environment: dict[str, object] = {
        "kind": "web",
        "id": "browser",
        "host": settings.hai_browser_host,
        "start_url": start_url or settings.hai_browser_start_url,
        "headless": settings.hai_browser_headless,
    }
    if settings.hai_browser_persist_login:
        environment["use_default_browser_profile"] = True
        environment["persist_browser_profile"] = True
    return environment


def inline_web_agent(
    *,
    name: str,
    description: str,
    model: str,
    instructions: str,
    start_url: str | None = None,
    skills: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    """A full inline agent definition for run_session, per the H Agents schema.

    Deliberately never sets `answer_format`: the SDK's `answer_schema` run parameter owns
    that field and raises on conflict.
    """
    agent: dict[str, object] = {
        # H requires lowercase alphanumerics and hyphens (so post_event -> post-event).
        "name": name.replace("_", "-"),
        "description": description,
        "model": model,
        "instructions": instructions,
        "environments": [browser_environment(start_url)],
    }
    if skills:
        agent["skills"] = skills
    return agent
