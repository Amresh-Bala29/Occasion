"""Per-event memory store.

One event's working memory: a small key→value store holding the stage outputs a workflow
would otherwise drop when it returns, so a re-run can resume from the last completed stage
instead of restarting the expensive H sessions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from database.repositories.memory_repository import MemoryRepository

# Well-known slots a workflow snapshots. Named here so reads and writes never drift on a
# bare string literal.
REQUIREMENTS = "requirements"
PLAN_SNAPSHOT = "plan_snapshot"
OPEN_QUESTIONS = "open_questions"
SHORTLIST = "shortlist"


class EventMemory:
    """A key/value view of one event's working memory. Values must be JSON-serializable."""

    def __init__(self, repo: MemoryRepository, event_id: str) -> None:
        self._repo = repo
        self._event_id = event_id

    def get(self, key: str) -> Any | None:
        """The stored value for `key`, or None if this event has nothing under it."""
        return self._repo.get_event_memory(self._event_id, key)

    def set(self, key: str, value: Any) -> None:
        """Store (or replace) `value` under `key` for this event."""
        self._repo.set_event_memory(event_id=self._event_id, key=key, value=value)

    def all(self) -> dict[str, Any]:
        """Every key/value this event has stored."""
        return self._repo.all_event_memory(self._event_id)
