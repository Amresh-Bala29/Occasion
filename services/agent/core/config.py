"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os


class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "")
    agent_port: int = int(os.getenv("AGENT_PORT", "8000"))
    h_api_key: str = os.getenv("H_API_KEY", "")
    gradium_api_key: str = os.getenv("GRADIUM_API_KEY", "")


settings = Settings()
