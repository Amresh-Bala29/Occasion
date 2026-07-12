"""Data access for background agent runs.

One repository over the `agent_runs` table: insert a row when a run starts, settle
it when the run finishes, and read it back for polling clients. Like the other
repositories, every write commits immediately so a run's lifecycle is durable the
moment it changes — a polling client never sees an in-between state.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from database import models as orm
from integrations.h_company.schemas import SessionResult

RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
INTERRUPTED = "interrupted"


class RunRecord(BaseModel):
    """One run as polling clients see it — snake_case, like every agentic surface."""

    id: str
    event_id: str | None = None
    kind: str
    title: str
    status: str
    agent: str | None = None
    reason: str | None = None
    result: SessionResult | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


class RunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, *, run_id: str, kind: str, title: str, event_id: str | None) -> RunRecord:
        row = orm.AgentRunRow(id=run_id, event_id=event_id, kind=kind, title=title, status=RUNNING)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)  # load the server-side created_at
        return _record(row)

    def finish(
        self,
        run_id: str,
        *,
        status: str,
        agent: str | None = None,
        reason: str | None = None,
        result: dict | None = None,
    ) -> None:
        row = self.db.get(orm.AgentRunRow, run_id)
        if row is None:
            return
        row.status = status
        row.agent = agent
        row.reason = reason
        row.result = result
        row.finished_at = func.now()
        self.db.commit()

    def get(self, run_id: str) -> RunRecord | None:
        row = self.db.get(orm.AgentRunRow, run_id)
        return _record(row) if row is not None else None

    def list_for_event(self, event_id: str, *, kind: str | None = None, limit: int = 200) -> list[RunRecord]:
        """This event's most recent runs, oldest first — the durable log a chat thread rebuilds from."""
        stmt = select(orm.AgentRunRow).where(orm.AgentRunRow.event_id == event_id)
        if kind is not None:
            stmt = stmt.where(orm.AgentRunRow.kind == kind)
        # The newest rows win the limit; reversing restores chronological order for the thread.
        stmt = stmt.order_by(orm.AgentRunRow.created_at.desc()).limit(limit)
        return [_record(row) for row in reversed(self.db.scalars(stmt).all())]

    def list_interrupted(self, *, kind: str | None = None, limit: int = 100) -> list[RunRecord]:
        """Runs a dead process stranded, oldest first — the boot reconciler's worklist."""
        stmt = select(orm.AgentRunRow).where(orm.AgentRunRow.status == INTERRUPTED)
        if kind is not None:
            stmt = stmt.where(orm.AgentRunRow.kind == kind)
        stmt = stmt.order_by(orm.AgentRunRow.created_at).limit(limit)
        return [_record(row) for row in self.db.scalars(stmt).all()]

    def interrupt_stale(self) -> int:
        """Mark runs a dead process left `running` as interrupted; returns how many."""
        stmt = (
            update(orm.AgentRunRow)
            .where(orm.AgentRunRow.status == RUNNING)
            .values(status=INTERRUPTED, finished_at=func.now())
        )
        count = self.db.execute(stmt).rowcount
        self.db.commit()
        return count


def _record(row: orm.AgentRunRow) -> RunRecord:
    return RunRecord(
        id=row.id,
        event_id=row.event_id,
        kind=row.kind,
        title=row.title,
        status=row.status,
        agent=row.agent,
        reason=row.reason,
        result=SessionResult.model_validate(row.result) if row.result is not None else None,
        created_at=row.created_at,
        finished_at=row.finished_at,
    )
