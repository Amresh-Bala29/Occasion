"""Vector store interface for semantic memory.

Semantic recall is backed by Postgres full-text search today — no embeddings, no pgvector.
Documents are stored verbatim and matched with to_tsvector/plainto_tsquery, ranked by
ts_rank (see MemoryRepository.search). The name and the add_document/search surface keep a
clean seam for an embedding-backed upgrade later, if an embedding source is ever adopted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from database.repositories.memory_repository import MemoryRepository


# Document kinds written by one module and recalled by another (core/runs.py files them,
# Memory.prompt_context reads them back); named here so the two never drift on a literal.
CHAT_NOTE = "chat"
DECISION = "decision"


def event_scope(event_id: str, suffix: str | None = None) -> str:
    """Scope string for a document tied to one event, optionally narrowed (e.g. by category)."""
    return f"event:{event_id}:{suffix}" if suffix else f"event:{event_id}"


def vendor_scope(vendor_key: str) -> str:
    """Scope string for a document tied to one vendor across events."""
    return f"vendor:{vendor_key}"


def user_scope(user_id: str) -> str:
    """Scope string for a document tied to one user across events."""
    return f"user:{user_id}"


class MemoryDocument(BaseModel):
    """One stored piece of text the agent can recall later. Internal to the backend."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    scope: str
    kind: str
    content: str
    metadata: dict[str, Any] = {}
    event_id: str | None = None


class MemoryHit(BaseModel):
    """A search match: the document and its full-text relevance rank (higher is better)."""

    document: MemoryDocument
    rank: float


class SemanticMemory:
    """Adds and recalls free-text memories via Postgres full-text search."""

    def __init__(self, repo: MemoryRepository) -> None:
        self._repo = repo

    def add_document(
        self,
        content: str,
        *,
        scope: str,
        kind: str,
        event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryDocument:
        """Store `content` so it can be recalled by `search`. Build `scope` with the helpers above."""
        return self._repo.add_document(
            scope=scope, kind=kind, content=content, event_id=event_id, metadata=metadata or {}
        )

    def search(self, query: str, *, scope: str | None = None, limit: int = 5) -> list[MemoryHit]:
        """The best full-text matches for `query`, most relevant first, optionally within `scope`."""
        return self._repo.search(query=query, scope=scope, limit=limit)

    def list(self, *, scope: str, kind: str, limit: int = 10) -> list[MemoryDocument]:
        """Every `kind` document filed under exactly `scope`, oldest first — recall that must
        not depend on matching a query (e.g. the event's recorded decisions)."""
        return self._repo.list_documents(scope=scope, kind=kind, limit=limit)
