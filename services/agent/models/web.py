"""Response models for the web app's dashboard API.

These mirror the TypeScript interfaces in apps/web/types/index.ts one-for-one, in
the same order. Fields are snake_case and serialize to camelCase via the shared
`to_camel` alias, so the JSON matches the frontend contract without any TS changes.
Optional fields default to None and are dropped by `response_model_exclude_none` on
the routes, matching the mock (which omits, never nulls, absent fields).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


# ---- Overview dashboard ----


class EventOverview(CamelModel):
    id: str
    kind: str
    name: str
    short_name: str
    status_label: str
    date: str
    location: str
    headcount: str
    days_to_go: str
    percent_complete: int


class BudgetOverview(CamelModel):
    total_usd: int
    paid_usd: int
    pending_usd: int


class VendorOverview(CamelModel):
    confirmed: int
    total: int
    in_progress: int


class ApprovalItem(CamelModel):
    id: str
    kind: str
    agent: str
    agent_tone: str
    tag: str
    title: str
    description: str
    amount: str
    vendor: str
    thread_id: str | None = None


class PendingApproval(ApprovalItem):
    """An unresolved approval joined to its event, for the cross-event approvals list."""

    event_id: str
    event_name: str


class AgentStatus(CamelModel):
    name: str
    tone: str
    status: str


class ActivityItem(CamelModel):
    id: str
    agent: str
    tone: str
    time_ago: str
    description: str


class DashboardData(CamelModel):
    event: EventOverview
    budget: BudgetOverview
    vendors: VendorOverview
    approvals: list[ApprovalItem]
    agents: list[AgentStatus]
    activity: list[ActivityItem]
    agents_working: int
    messages_count: int
    auto_approve_limit: str


# ---- Vendors tab ----


class Vendor(CamelModel):
    id: str
    initials: str
    name: str
    category: str
    status: str
    quotes: int
    last_activity: str
    cost: str


# ---- Plan tab ----


class PlanPhase(CamelModel):
    name: str
    percent: int
    note: str


class PlanTask(CamelModel):
    id: str
    label: str
    done: bool


class PlanTaskGroup(CamelModel):
    name: str
    owner: str
    tone: str
    tasks: list[PlanTask]


class RiskItem(CamelModel):
    level: str
    title: str
    mitigation: str


class Milestone(CamelModel):
    title: str
    when: str
    done: bool


class EventPlan(CamelModel):
    phases: list[PlanPhase]
    groups: list[PlanTaskGroup]
    risks: list[RiskItem]
    milestones: list[Milestone]


# ---- Budget tab ----


class BudgetCategory(CamelModel):
    name: str
    committed_usd: int
    paid_usd: int
    estimate: bool | None = None


class SavingSuggestion(CamelModel):
    title: str
    amount: str
    note: str


class BudgetDetail(CamelModel):
    categories: list[BudgetCategory]
    savings: list[SavingSuggestion]
    savings_footnote: str


# ---- Calendar tab and deadline lists ----


class CalendarEventItem(CamelModel):
    date: str
    title: str
    kind: str


class DeadlineItem(CamelModel):
    id: str
    month: str
    day: str
    title: str
    meta: str
    emphasis: str | None = None


# ---- Approvals tab ----


class DecisionRecord(CamelModel):
    id: str
    title: str
    amount: str
    when: str
    approved: bool


class SpendingRule(CamelModel):
    id: str
    label: str
    value: str


# ---- Post-event tab ----


class PostEventTask(CamelModel):
    id: str
    glyph: str
    title: str
    description: str
    state: str


# ---- Unified inbox ----


class InboxMessage(CamelModel):
    id: str
    author: str
    from_me: bool | None = None
    day: str
    time: str
    body: str


class Conversation(CamelModel):
    id: str
    name: str
    subtitle: str
    channel: str
    avatar_initials: str
    time_label: str
    preview: str
    unread: bool
    archived: bool
    quick_replies: list[str]
    messages: list[InboxMessage]
