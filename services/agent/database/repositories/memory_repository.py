"""Data access for agent memory.

One repository owns the four memory aggregates: cross-event user preferences and vendor
reputation, per-event working memory, and the full-text document store. It mirrors
EventRepository — a Session is injected and held as `self.db`, writes commit per call, and
reads return the memory-package Pydantic models. Semantic search uses built-in Postgres
full-text (to_tsvector / plainto_tsquery / ts_rank); there are no embeddings.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.orm import Session

from database import models as orm
from memory.user_preferences import UserPreferences
from memory.vector_store import MemoryDocument, MemoryHit
from memory.vendor_memory import VendorReputation

# Engagement kind -> the counter it bumps. The one place the vocabulary is enumerated.
_ENGAGEMENT_COUNTERS = {"contacted": "times_contacted", "quoted": "times_quoted", "booked": "times_booked"}

# The text-search config, emitted as a SQL constant (not a bind parameter) so the search
# expression matches the migration's `to_tsvector('english', content)` GIN index — a bound
# regconfig would bypass the index and fail to resolve the to_tsvector overload.
_TS_CONFIG = literal_column("'english'")


class MemoryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- User preferences ----

    def get_user_preferences(self, user_id: str) -> UserPreferences | None:
        row = self.db.get(orm.UserPreferenceRow, user_id)
        return UserPreferences.model_validate(row) if row is not None else None

    def upsert_user_preferences(self, prefs: UserPreferences) -> UserPreferences:
        row = self.db.get(orm.UserPreferenceRow, prefs.user_id)
        if row is None:
            row = orm.UserPreferenceRow(user_id=prefs.user_id)
            self.db.add(row)
        row.dietary_restrictions = prefs.dietary_restrictions
        row.food_preferences = prefs.food_preferences
        row.entertainment_preferences = prefs.entertainment_preferences
        row.accessibility_needs = prefs.accessibility_needs
        row.priorities = prefs.priorities
        row.preferred_vendors = prefs.preferred_vendors
        row.blocked_vendors = prefs.blocked_vendors
        row.branding_notes = prefs.branding_notes
        self.db.commit()
        return UserPreferences.model_validate(row)

    # ---- Vendor reputation ----

    def get_vendor_reputation(self, vendor_key: str) -> VendorReputation | None:
        row = self.db.get(orm.VendorReputationRow, vendor_key)
        return VendorReputation.model_validate(row) if row is not None else None

    def record_engagement(
        self,
        *,
        vendor_key: str,
        name: str,
        kind: str,
        category: str | None = None,
        url: str | None = None,
        event_id: str | None = None,
        note: str | None = None,
    ) -> VendorReputation:
        """Bump the counter for `kind`, append the engagement to the history, and persist.

        Creates the vendor's reputation row on first contact. Later engagements freshen the
        identity fields, since research often finds better name/URL data over time.
        """
        counter = _ENGAGEMENT_COUNTERS.get(kind)
        if counter is None:
            raise ValueError(f"unknown engagement kind {kind!r}")
        row = self.db.get(orm.VendorReputationRow, vendor_key)
        if row is None:
            # Initialize the counters explicitly: the column `default=0` isn't applied until
            # flush, but the increment below reads them first.
            row = orm.VendorReputationRow(
                vendor_key=vendor_key,
                name=name,
                category=category,
                url=url,
                times_contacted=0,
                times_quoted=0,
                times_booked=0,
                history=[],
            )
            self.db.add(row)
        else:
            row.name = name or row.name
            row.category = category or row.category
            row.url = url or row.url
        setattr(row, counter, getattr(row, counter) + 1)
        # JSONB mutations aren't tracked in place; reassign so SQLAlchemy sees the change.
        row.history = [*row.history, {"event_id": event_id, "kind": kind, "note": note}]
        self.db.commit()
        return VendorReputation.model_validate(row)

    def top_vendors(self, *, category: str, limit: int = 5) -> list[VendorReputation]:
        stmt = (
            select(orm.VendorReputationRow)
            .where(orm.VendorReputationRow.category == category)
            .order_by(orm.VendorReputationRow.times_booked.desc())
            .limit(limit)
        )
        return [VendorReputation.model_validate(row) for row in self.db.scalars(stmt).all()]

    # ---- Event working memory ----

    def get_event_memory(self, event_id: str, key: str) -> Any | None:
        row = self.db.get(orm.EventMemoryRow, (event_id, key))
        return row.value if row is not None else None

    def set_event_memory(self, *, event_id: str, key: str, value: Any) -> None:
        row = self.db.get(orm.EventMemoryRow, (event_id, key))
        if row is None:
            self.db.add(orm.EventMemoryRow(event_id=event_id, key=key, value=value))
        else:
            row.value = value
        self.db.commit()

    def all_event_memory(self, event_id: str) -> dict[str, Any]:
        stmt = select(orm.EventMemoryRow).where(orm.EventMemoryRow.event_id == event_id)
        return {row.key: row.value for row in self.db.scalars(stmt).all()}

    # ---- Semantic documents (Postgres full-text) ----

    def add_document(
        self,
        *,
        scope: str,
        kind: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> MemoryDocument:
        row = orm.MemoryDocumentRow(scope=scope, kind=kind, content=content, meta=metadata or {}, event_id=event_id)
        self.db.add(row)
        self.db.commit()
        return _document(row)

    def search(self, *, query: str, scope: str | None = None, limit: int = 5) -> list[MemoryHit]:
        """The best full-text matches for `query`, ranked by ts_rank, most relevant first.

        `scope` matches hierarchically: `event:<id>` also recalls `event:<id>:<category>`
        documents, so an event-level search sees every document filed under that event.
        """
        tsquery = func.plainto_tsquery(_TS_CONFIG, query)
        document = func.to_tsvector(_TS_CONFIG, orm.MemoryDocumentRow.content)
        rank = func.ts_rank(document, tsquery)
        stmt = select(orm.MemoryDocumentRow, rank.label("rank")).where(document.op("@@")(tsquery))
        if scope is not None:
            stmt = stmt.where(
                or_(orm.MemoryDocumentRow.scope == scope, orm.MemoryDocumentRow.scope.like(f"{scope}:%"))
            )
        stmt = stmt.order_by(rank.desc()).limit(limit)
        return [MemoryHit(document=_document(row), rank=float(score)) for row, score in self.db.execute(stmt).all()]


def _document(row: orm.MemoryDocumentRow) -> MemoryDocument:
    # Built by hand rather than model_validate: the ORM attribute is `meta` (the DB column
    # is `metadata`), so from_attributes would read the wrong name for the metadata field.
    return MemoryDocument(
        id=row.id, scope=row.scope, kind=row.kind, content=row.content, metadata=row.meta, event_id=row.event_id
    )
