"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load the agent service's local .env (services/agent/.env) so settings resolve from it.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    hai_api_key: str = os.getenv("HAI_API_KEY", "")

    # H exposes two API hosts: OpenAI-compatible completions on the Models API, and
    # computer-use sessions on the AGP host. HAI_SESSION_BASE_URL selects the session
    # region: https://agp.hcompany.ai for US (North America), or empty to fall back to
    # the SDK's default region (EU, agp.eu.hcompany.ai). A non-empty value is forwarded
    # to the SDK's Client(base_url=...) verbatim, so this env var is the region switch.
    hai_models_base_url: str = os.getenv("HAI_MODELS_BASE_URL", "https://api.hcompany.ai/v1")
    hai_session_base_url: str = os.getenv("HAI_SESSION_BASE_URL", "")

    # Gradium voice API (objective 20): STT/TTS over REST. Auth uses an x-api-key header.
    gradium_api_key: str = os.getenv("GRADIUM_API_KEY", "")
    gradium_base_url: str = os.getenv("GRADIUM_BASE_URL", "https://api.gradium.ai/api")

    # H browser: a cloud Chrome that opens Google and reuses a signed-in profile, so H drives
    # Gmail/Calendar/Luma/etc. directly instead of via per-service API keys.
    hai_browser_host: str = os.getenv("HAI_BROWSER_HOST", "cloud")
    hai_browser_start_url: str = os.getenv("HAI_BROWSER_START_URL", "https://www.google.com")
    hai_browser_headless: bool = os.getenv("HAI_BROWSER_HEADLESS", "false").lower() == "true"
    hai_browser_persist_login: bool = os.getenv("HAI_BROWSER_PERSIST_LOGIN", "true").lower() == "true"

    # Guardrail policy (objective 19): the signed-in surfaces the agents may act on, and
    # actions they must never take autonomously. core/security.py wraps these as the
    # checks and the prompt-level domain guardrail; hard blocks live in the approvals layer.
    allowed_domains: tuple[str, ...] = (
        "lu.ma",
        "partiful.com",
        "eventbrite.com",
        "meetup.com",
        "mail.google.com",
        "calendar.google.com",
    )
    blocked_actions: tuple[str, ...] = (
        "purchase_without_approval",
        "submit_payment_form",
    )


settings = Settings()
