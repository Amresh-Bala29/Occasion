"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load the agent service's local .env (services/agent/.env) so settings resolve from it.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    agent_port: int = int(os.getenv("AGENT_PORT", "8000"))
    hai_api_key: str = os.getenv("HAI_API_KEY", "")
    hai_base_url: str = os.getenv("HAI_BASE_URL", "")
    gradium_api_key: str = os.getenv("GRADIUM_API_KEY", "")

    # H browser: a cloud Chrome that opens Google and reuses a signed-in profile, so H drives
    # Gmail/Calendar/Luma/etc. directly instead of via per-service API keys.
    hai_browser_host: str = os.getenv("HAI_BROWSER_HOST", "cloud")
    hai_browser_start_url: str = os.getenv("HAI_BROWSER_START_URL", "https://www.google.com")
    hai_browser_headless: bool = os.getenv("HAI_BROWSER_HEADLESS", "false").lower() == "true"
    hai_browser_persist_login: bool = os.getenv("HAI_BROWSER_PERSIST_LOGIN", "true").lower() == "true"


settings = Settings()
