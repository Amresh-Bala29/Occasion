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

from typing import TYPE_CHECKING, Any

from memory.event_memory import PLAN_SNAPSHOT, REQUIREMENTS, EventMemory
from memory.user_preferences import PreferencesMemory
from memory.vector_store import DECISION, SemanticMemory, event_scope
from memory.vendor_memory import VendorMemory

if TYPE_CHECKING:
    from database.repositories.memory_repository import MemoryRepository

# Bounds for prompt context: a handful of relevant notes, each trimmed so one verbose
# research report can't crowd the actual task out of an agent's prompt.
_RECALL_LIMIT = 3
_RECALL_MAX_CHARS = 800


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

    def prompt_context(self, event_id: str, query: str, *, user_id: str | None = None) -> str | None:
        """What an agent taking on `query` for this event should already know.

        One prompt-ready block drawn from everything persisted for the event: the
        captured brief, the plan's summary, recorded decisions, the user's long-term
        preferences, and the notes most relevant to the task. None when memory holds
        nothing yet, so callers can skip the section entirely.
        """
        working = self.event(event_id).all()
        sections: list[str] = []
        brief = _brief_lines(working.get(REQUIREMENTS))
        if brief:
            sections.append("Event brief on file:\n" + "\n".join(brief))
        plan = working.get(PLAN_SNAPSHOT)
        if isinstance(plan, dict) and plan.get("event_summary"):
            sections.append(f"Plan summary: {plan['event_summary']}")
        decisions = self.semantic.list(scope=event_scope(event_id), kind=DECISION)
        if decisions:
            sections.append("Decisions already made:\n" + "\n".join(f"- {doc.content}" for doc in decisions))
        note = self.preferences.get(user_id).as_prompt_note()
        if note:
            sections.append(note)
        recalled = self._recalled_notes(event_id, query, skip={doc.id for doc in decisions})
        if recalled:
            sections.append("Notes from earlier work on this event:\n" + "\n\n".join(recalled))
        return "\n\n".join(sections) if sections else None

    def _recalled_notes(self, event_id: str, query: str, *, skip: set[int | None]) -> list[str]:
        """The most relevant stored notes for `query`, trimmed for prompt use.

        `skip` holds document ids already placed in the block (decisions ride along
        unconditionally), so a strong search match can't duplicate them.
        """
        notes = []
        for hit in self.semantic.search(query, scope=event_scope(event_id), limit=_RECALL_LIMIT):
            if hit.document.id in skip:
                continue
            content = hit.document.content
            if len(content) > _RECALL_MAX_CHARS:
                content = f"{content[:_RECALL_MAX_CHARS]}…"
            notes.append(content)
        return notes


def _brief_lines(snapshot: Any) -> list[str]:
    """The stored requirements snapshot as readable lines; empty when missing or malformed.

    Rendered generically from the stored dict (not the EventRequirements model) so a
    field added to the schema reaches prompts without touching this code.
    """
    if not isinstance(snapshot, dict):
        return []
    lines = []
    for field, value in snapshot.items():
        # open_questions is interview state, not a fact about the event.
        if field == "open_questions" or value in (None, "", []):
            continue
        rendered = ", ".join(str(item) for item in value) if isinstance(value, list) else value
        lines.append(f"- {field.replace('_', ' ')}: {rendered}")
    return lines
