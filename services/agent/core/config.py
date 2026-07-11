"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load the agent service's local .env (services/agent/.env) so settings resolve from it.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "")
    agent_port: int = int(os.getenv("AGENT_PORT", "8000"))
    hai_api_key: str = os.getenv("HAI_API_KEY", "")
    hai_base_url: str = os.getenv("HAI_BASE_URL", "")
    gradium_api_key: str = os.getenv("GRADIUM_API_KEY", "")


settings = Settings()
