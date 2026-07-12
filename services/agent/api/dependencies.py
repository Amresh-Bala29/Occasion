"""Shared FastAPI dependencies (database sessions, repositories, supervisor, orchestrator)."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from core.orchestrator import Orchestrator
from core.runs import RunManager, run_manager
from core.state import Memory
from core.supervisor import Supervisor
from database.connection import new_session
from database.repositories.event_repository import EventRepository
from database.repositories.memory_repository import MemoryRepository
from database.repositories.run_repository import RunRepository


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


def get_orchestrator(db: Session = Depends(get_db)) -> Orchestrator:
    # Memory rides the request's session (get_db is cached per request), and
    # MemoryRepository commits per call, so nothing is left pending at response time.
    return Orchestrator(memory=Memory(MemoryRepository(db)))


def get_run_repository(db: Session = Depends(get_db)) -> RunRepository:
    return RunRepository(db)


def get_run_manager() -> RunManager:
    # The process-wide manager: background runs outlive the request that started them.
    return run_manager
