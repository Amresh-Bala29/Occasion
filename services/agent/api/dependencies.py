"""Shared FastAPI dependencies (auth, database sessions, current user)."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

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
