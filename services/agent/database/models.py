"""SQLAlchemy ORM models for the event workspace.

The whole schema is one `events` aggregate: every table below hangs off an event,
and the child lists (task groups → tasks, conversations → messages) hang off those.

Attribute names are the snake_case of the web app's TypeScript fields (types/index.ts)
so the Pydantic response DTOs in models/web.py can read them straight through and
re-emit camelCase. A few columns are renamed off reserved/type words (`when`, `time`,
`date`) to keep the hand-written migration SQL quote-free. Slugs stay as text primary
keys because the frontend routes and localStorage keys depend on them; id-less display
rows get a synthetic integer key that never reaches the API. Every list carries an
`ordinal` so reads can restore the exact mock order (Postgres row order is undefined).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str] = mapped_column(Text)
    status_label: Mapped[str] = mapped_column(Text)
    date: Mapped[str] = mapped_column("event_date", Text)
    location: Mapped[str] = mapped_column(Text)
    headcount: Mapped[str] = mapped_column(Text)
    days_to_go: Mapped[str] = mapped_column(Text)
    percent_complete: Mapped[int] = mapped_column(Integer)
    # Overview aggregates are stored verbatim, not derived: the mock's headline
    # figures deliberately do not reconcile with the detail tables.
    total_usd: Mapped[int] = mapped_column(Integer)
    paid_usd: Mapped[int] = mapped_column(Integer)
    pending_usd: Mapped[int] = mapped_column(Integer)
    vendors_confirmed: Mapped[int] = mapped_column(Integer)
    vendors_total: Mapped[int] = mapped_column(Integer)
    vendors_in_progress: Mapped[int] = mapped_column(Integer)
    auto_approve_limit: Mapped[str] = mapped_column(Text)
    savings_footnote: Mapped[str] = mapped_column(Text)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    agent: Mapped[str] = mapped_column(Text)
    agent_tone: Mapped[str] = mapped_column(Text)
    tag: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[str] = mapped_column(Text)
    vendor: Mapped[str] = mapped_column(Text)
    thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    ordinal: Mapped[int] = mapped_column(Integer)
    # The machine-readable action this approval authorizes (e.g. a book_vendor spec);
    # display-only approvals leave it null and resolve without executing anything.
    action: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class AgentStatusRow(Base):
    __tablename__ = "agent_status"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)


class ActivityItem(Base):
    __tablename__ = "activity_items"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    agent: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(Text)
    time_ago: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    # false = the dashboard's live feed; true = the rotating simulated pool.
    pool: Mapped[bool] = mapped_column(Boolean, default=False)
    ordinal: Mapped[int] = mapped_column(Integer)


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    initials: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    quotes: Mapped[int] = mapped_column(Integer)
    last_activity: Mapped[str] = mapped_column(Text)
    cost: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)


class PlanPhase(Base):
    __tablename__ = "plan_phases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    percent: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)


class PlanTaskGroup(Base):
    __tablename__ = "plan_task_groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)


class PlanTask(Base):
    __tablename__ = "plan_tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("plan_task_groups.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(Text)
    done: Mapped[bool] = mapped_column(Boolean)
    ordinal: Mapped[int] = mapped_column(Integer)


class RiskItem(Base):
    __tablename__ = "risks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    mitigation: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)


class Milestone(Base):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    when: Mapped[str] = mapped_column("when_label", Text)
    done: Mapped[bool] = mapped_column(Boolean)
    ordinal: Mapped[int] = mapped_column(Integer)


class BudgetCategory(Base):
    __tablename__ = "budget_categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    committed_usd: Mapped[int] = mapped_column(Integer)
    paid_usd: Mapped[int] = mapped_column(Integer)
    # Null (not false) when absent, so the DTO omits it to match the mock.
    estimate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer)


class SavingSuggestion(Base):
    __tablename__ = "saving_suggestions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    amount: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    date: Mapped[str] = mapped_column("event_date", Text)
    title: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)


class DeadlineItem(Base):
    __tablename__ = "deadline_items"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    # Which list this row belongs to: 'agenda' (calendar rail) or 'key' (overview).
    list_kind: Mapped[str] = mapped_column(Text)
    month: Mapped[str] = mapped_column(Text)
    day: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    meta: Mapped[str] = mapped_column(Text)
    emphasis: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer)


class DecisionRecord(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    amount: Mapped[str] = mapped_column(Text)
    when: Mapped[str] = mapped_column("when_label", Text)
    approved: Mapped[bool] = mapped_column(Boolean)
    # Lower sorts first; new decisions from resolved approvals get min-1 to lead.
    ordinal: Mapped[int] = mapped_column(Integer)


class SpendingRule(Base):
    __tablename__ = "spending_rules"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)


class PostEventTask(Base):
    __tablename__ = "post_event_tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    glyph: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    subtitle: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    avatar_initials: Mapped[str] = mapped_column(Text)
    time_label: Mapped[str] = mapped_column(Text)
    preview: Mapped[str] = mapped_column(Text)
    unread: Mapped[bool] = mapped_column(Boolean)
    archived: Mapped[bool] = mapped_column(Boolean)
    quick_replies: Mapped[list[str]] = mapped_column(JSONB)
    ordinal: Mapped[int] = mapped_column(Integer)


class InboxMessage(Base):
    __tablename__ = "inbox_messages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    author: Mapped[str] = mapped_column(Text)
    from_me: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    day: Mapped[str] = mapped_column(Text)
    time: Mapped[str] = mapped_column("time_label", Text)
    body: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer)


# ---- Agent memory (backend-internal; not part of the events display aggregate) ----
#
# These back the agent fleet's memory rather than the dashboard, so they carry no
# `ordinal`: order comes from relevance or identity, not a fixed display list. Cross-event
# rows (preferences, vendor reputation) are not event-scoped; per-event working memory and
# documents cascade off the event.


class UserPreferenceRow(Base):
    """One user's long-term preferences, accumulated across their events."""

    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    dietary_restrictions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    food_preferences: Mapped[list[str]] = mapped_column(JSONB, default=list)
    entertainment_preferences: Mapped[list[str]] = mapped_column(JSONB, default=list)
    accessibility_needs: Mapped[list[str]] = mapped_column(JSONB, default=list)
    priorities: Mapped[list[str]] = mapped_column(JSONB, default=list)
    preferred_vendors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    blocked_vendors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    branding_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class VendorReputationRow(Base):
    """A vendor's reputation across every event we've used them on, keyed by a domain/name
    slug — distinct from the per-event `vendors` display table above."""

    __tablename__ = "vendor_reputation"

    vendor_key: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    times_contacted: Mapped[int] = mapped_column(Integer, default=0)
    times_quoted: Mapped[int] = mapped_column(Integer, default=0)
    times_booked: Mapped[int] = mapped_column(Integer, default=0)
    reliability_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    history: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventMemoryRow(Base):
    """One event's working memory as a key/value store; composite (event_id, key) primary key."""

    __tablename__ = "event_memory"

    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)


class MemoryDocumentRow(Base):
    """A free-text memory recalled via Postgres full-text search (see memory/vector_store.py).

    The Python attribute is `meta`, not `metadata`: DeclarativeBase reserves that name. The
    column stays `metadata`, renamed via the first positional arg like the reserved-word
    columns above.
    """

    __tablename__ = "memory_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(Text)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


# ---- Runtime execution (backend-internal) ----


class AgentRunRow(Base):
    """One background agent run: a chat turn or an approved action being executed.

    Rows are the durable side of core/runs.py — inserted `running`, settled to
    completed/failed by the executing task, and swept to `interrupted` on boot if a
    dead process left them behind. `result` holds the run's SessionResult dump.
    """

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebhookEventRow(Base):
    """One inbound webhook, persisted verbatim for audit before any processing exists."""

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
