"""Current workflow state and shared run context.

`Memory` is the run's single memory handle: one database Session behind four typed
accessors that the orchestrator and workflows read and write during a run. It is
constructor-injected with a MemoryRepository, so tests swap in a fake through the same seam.

Thread-safety: a SQLAlchemy Session is not thread-safe, and the orchestrator fans agents
out via asyncio.to_thread. All memory reads and writes therefore happen in orchestrator and
workflow coroutine code, on the event-loop thread — never inside an agent's threaded H call.
Agents receive this handle as their `context` and may read it in build_prompt (which runs on
the loop, before the thread hop); the write choreography stays workflow-owned.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from memory.event_memory import EventMemory
from memory.user_preferences import PreferencesMemory
from memory.vector_store import SemanticMemory
from memory.vendor_memory import VendorMemory

if TYPE_CHECKING:
    from database.repositories.memory_repository import MemoryRepository


class Memory:
    """One run's memory, exposed as four typed accessors over a shared repository."""

    def __init__(self, repo: MemoryRepository) -> None:
        self._repo = repo
        self.preferences = PreferencesMemory(repo)
        self.vendors = VendorMemory(repo)
        self.semantic = SemanticMemory(repo)

    def event(self, event_id: str) -> EventMemory:
        """This event's working memory — a key/value store scoped to `event_id`."""
        return EventMemory(self._repo, event_id)
