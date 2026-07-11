"""Event domain model."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Event(BaseModel):
    id: str
    name: str
    date: datetime | None = None
    budget: float | None = None
    location: str | None = None
