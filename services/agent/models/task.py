"""Task domain model."""

from __future__ import annotations

from pydantic import BaseModel


class Task(BaseModel):
    id: str
    event_id: str
    title: str
    status: str = "pending"
    assignee_agent: str | None = None
