"""Task domain model."""

from __future__ import annotations

from pydantic import BaseModel


class Task(BaseModel):
    id: str
    event_id: str
    title: str
    status: str = "pending"
    assignee_agent: str | None = None
    # Who the task is for, so preference memory can attribute what's learned. Optional while
    # auth is deferred; memory falls back to a single-user default when it's absent.
    user_id: str | None = None
