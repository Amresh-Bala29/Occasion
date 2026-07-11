"""Marketing prompt model — structured input for marketing asset generation."""

from __future__ import annotations

from pydantic import BaseModel


class MarketingPrompt(BaseModel):
    event_id: str
    audience: str
    tone: str = "friendly"
    channels: list[str] = []
