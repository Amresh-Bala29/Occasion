"""Shared FastAPI dependencies (database sessions, repositories, supervisor)."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from core.supervisor import Supervisor
from database.connection import new_session
from database.repositories.event_repository import EventRepository


def get_db() -> Iterator[Session]:
    db = new_session()
    try:
        yield db
    finally:
        db.close()


def get_event_repository(db: Session = Depends(get_db)) -> EventRepository:
    return EventRepository(db)


def get_supervisor() -> Supervisor:
    # Per-request construction, like per-run HClient.from_settings(); the key guard
    # lives in the supervisor's own methods.
    return Supervisor.from_settings()
