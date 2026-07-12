"""Data access for the event workspace.

One repository owns the whole `events` aggregate: a read method per web-app getter,
plus the three writes the approvals UI needs. Reads return the Pydantic response
models from models/web.py, ordered by each row's `ordinal` so the exact mock order is
restored. The composite dashboard stores its headline figures verbatim and computes
only the two that genuinely reconcile — `agentsWorking` and `messagesCount`.
"""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from database import models as orm
from database.repositories.run_repository import RUNNING
from memory.event_memory import DEMO_FIXTURE
from models import web

if TYPE_CHECKING:
    from agents.budget_agent import BudgetReview
    from agents.requirements_agent import EventRequirements
    from workflows.event_planning import EventPlan
    from workflows.vendor_outreach import QuoteComparison
    from workflows.vendor_sourcing import VendorShortlist

# "Purchasing agent" -> "Purchasing" for the decision/activity copy, matching the client.
_AGENT_SUFFIX = re.compile(r" agent$", re.IGNORECASE)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())[:40].strip("-")
    return slug or "action"


_PRICE = re.compile(r"\$\s?[\d,]+(?:\.\d+)?")


def _initials(name: str) -> str:
    words = name.split()
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return name[:2].upper()


def _cost_label(price_notes: str | None) -> str:
    # Research prices are estimates until a quote lands; the seed marks those with ~.
    match = _PRICE.search(price_notes or "")
    return f"~{match.group(0)}" if match else "—"


class EventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- Reads ----

    def list_events(self) -> list[web.EventOverview]:
        rows = self.db.scalars(select(orm.Event).order_by(orm.Event.name)).all()
        return [web.EventOverview.model_validate(event) for event in rows]

    def list_pending_approvals(self) -> list[web.PendingApproval]:
        # Ordinals are per-event (new rows lead at min-1), so the compound order here
        # is deterministic within each event; _ordered can't express the join.
        stmt = (
            select(orm.Approval, orm.Event.name)
            .join(orm.Event, orm.Event.id == orm.Approval.event_id)
            .where(orm.Approval.resolved.is_(False))
            .order_by(orm.Approval.event_id, orm.Approval.ordinal)
        )
        return [
            web.PendingApproval(
                **web.ApprovalItem.model_validate(approval).model_dump(),
                event_id=approval.event_id,
                event_name=event_name,
            )
            for approval, event_name in self.db.execute(stmt).all()
        ]

    def get_dashboard(self, event_id: str) -> web.DashboardData | None:
        # Display rows come from the fixture when flagged; the live-run count below stays on
        # the real event so the "agents working" badge reflects the browsers still running.
        source_id = self._resolve_demo(event_id)
        event = self.db.get(orm.Event, source_id)
        if event is None:
            return None

        approvals = self._ordered(
            orm.Approval, orm.Approval.event_id == source_id, orm.Approval.resolved.is_(False)
        )
        agents = self._ordered(orm.AgentStatusRow, orm.AgentStatusRow.event_id == source_id)
        activity = self._ordered(
            orm.ActivityItem, orm.ActivityItem.event_id == source_id, orm.ActivityItem.pool.is_(False)
        )
        messages_count = self.db.scalar(
            select(func.count())
            .select_from(orm.Conversation)
            .where(
                orm.Conversation.event_id == source_id,
                orm.Conversation.unread.is_(True),
                orm.Conversation.archived.is_(False),
            )
        )
        # In-flight runs are the live truth; the agent_status table is static showcase
        # copy with no runtime writer, so counting it reads 0 for every real event. The
        # boot sweep settles rows a dead process left `running`, so this can't leak.
        running_runs = self.db.scalar(
            select(func.count())
            .select_from(orm.AgentRunRow)
            .where(orm.AgentRunRow.event_id == event_id, orm.AgentRunRow.status == RUNNING)
        )

        return web.DashboardData(
            event=web.EventOverview.model_validate(event),
            budget=web.BudgetOverview.model_validate(event),
            vendors=web.VendorOverview(
                confirmed=event.vendors_confirmed,
                total=event.vendors_total,
                in_progress=event.vendors_in_progress,
            ),
            approvals=[web.ApprovalItem.model_validate(a) for a in approvals],
            agents=[web.AgentStatus.model_validate(a) for a in agents],
            activity=[web.ActivityItem.model_validate(a) for a in activity],
            agents_working=running_runs or 0,
            messages_count=messages_count or 0,
            auto_approve_limit=event.auto_approve_limit,
        )

    def get_vendors(self, event_id: str) -> list[web.Vendor]:
        event_id = self._resolve_demo(event_id)
        rows = self._ordered(orm.Vendor, orm.Vendor.event_id == event_id)
        return [web.Vendor.model_validate(v) for v in rows]

    def get_plan(self, event_id: str) -> web.EventPlan:
        event_id = self._resolve_demo(event_id)
        phases = self._ordered(orm.PlanPhase, orm.PlanPhase.event_id == event_id)
        groups = self._ordered(orm.PlanTaskGroup, orm.PlanTaskGroup.event_id == event_id)
        risks = self._ordered(orm.RiskItem, orm.RiskItem.event_id == event_id)
        milestones = self._ordered(orm.Milestone, orm.Milestone.event_id == event_id)

        group_dtos = []
        for group in groups:
            tasks = self._ordered(orm.PlanTask, orm.PlanTask.group_id == group.id)
            group_dtos.append(
                web.PlanTaskGroup(
                    name=group.name,
                    owner=group.owner,
                    tone=group.tone,
                    tasks=[web.PlanTask.model_validate(t) for t in tasks],
                )
            )

        return web.EventPlan(
            phases=[web.PlanPhase.model_validate(p) for p in phases],
            groups=group_dtos,
            risks=[web.RiskItem.model_validate(r) for r in risks],
            milestones=[web.Milestone.model_validate(m) for m in milestones],
        )

    def get_budget(self, event_id: str) -> web.BudgetDetail:
        event_id = self._resolve_demo(event_id)
        categories = self._ordered(orm.BudgetCategory, orm.BudgetCategory.event_id == event_id)
        savings = self._ordered(orm.SavingSuggestion, orm.SavingSuggestion.event_id == event_id)
        event = self.db.get(orm.Event, event_id)
        return web.BudgetDetail(
            categories=[web.BudgetCategory.model_validate(c) for c in categories],
            savings=[web.SavingSuggestion.model_validate(s) for s in savings],
            savings_footnote=event.savings_footnote if event else "",
        )

    def get_calendar_events(self, event_id: str) -> list[web.CalendarEventItem]:
        event_id = self._resolve_demo(event_id)
        rows = self._ordered(orm.CalendarEvent, orm.CalendarEvent.event_id == event_id)
        return [web.CalendarEventItem.model_validate(c) for c in rows]

    def get_agenda(self, event_id: str) -> list[web.DeadlineItem]:
        return self._deadlines(event_id, "agenda")

    def get_key_deadlines(self, event_id: str) -> list[web.DeadlineItem]:
        return self._deadlines(event_id, "key")

    def get_conversations(self, event_id: str) -> list[web.Conversation]:
        event_id = self._resolve_demo(event_id)
        conversations = self._ordered(orm.Conversation, orm.Conversation.event_id == event_id)
        result = []
        for convo in conversations:
            messages = self._ordered(orm.InboxMessage, orm.InboxMessage.conversation_id == convo.id)
            result.append(
                web.Conversation(
                    id=convo.id,
                    name=convo.name,
                    subtitle=convo.subtitle,
                    channel=convo.channel,
                    avatar_initials=convo.avatar_initials,
                    time_label=convo.time_label,
                    preview=convo.preview,
                    unread=convo.unread,
                    archived=convo.archived,
                    quick_replies=list(convo.quick_replies),
                    messages=[web.InboxMessage.model_validate(m) for m in messages],
                )
            )
        return result

    def get_decisions(self, event_id: str) -> list[web.DecisionRecord]:
        event_id = self._resolve_demo(event_id)
        rows = self._ordered(orm.DecisionRecord, orm.DecisionRecord.event_id == event_id)
        return [web.DecisionRecord.model_validate(d) for d in rows]

    def get_spending_rules(self, event_id: str) -> list[web.SpendingRule]:
        event_id = self._resolve_demo(event_id)
        rows = self._ordered(orm.SpendingRule, orm.SpendingRule.event_id == event_id)
        return [web.SpendingRule.model_validate(r) for r in rows]

    def get_auto_approve_limit(self, event_id: str) -> str | None:
        event_id = self._resolve_demo(event_id)
        event = self.db.get(orm.Event, event_id)
        return event.auto_approve_limit if event else None

    def get_post_event_tasks(self, event_id: str) -> list[web.PostEventTask]:
        event_id = self._resolve_demo(event_id)
        rows = self._ordered(orm.PostEventTask, orm.PostEventTask.event_id == event_id)
        return [web.PostEventTask.model_validate(t) for t in rows]

    def get_activity_pool(self, event_id: str) -> list[web.ActivityItem]:
        event_id = self._resolve_demo(event_id)
        rows = self._ordered(
            orm.ActivityItem, orm.ActivityItem.event_id == event_id, orm.ActivityItem.pool.is_(True)
        )
        return [web.ActivityItem.model_validate(a) for a in rows]

    def get_activity(self, event_id: str) -> list[web.ActivityItem]:
        event_id = self._resolve_demo(event_id)
        rows = self._ordered(
            orm.ActivityItem, orm.ActivityItem.event_id == event_id, orm.ActivityItem.pool.is_(False)
        )
        return [web.ActivityItem.model_validate(a) for a in rows]

    def get_approval_action(self, approval_id: str) -> dict | None:
        """The machine-readable action a still-pending approval authorizes, if any."""
        approval = self.db.get(orm.Approval, approval_id)
        if approval is None or approval.resolved:
            return None
        return approval.action

    # ---- Writes ----

    def create_event(self, *, name: str, kind: str, date: str, location: str, headcount: str) -> web.EventOverview:
        """Create a bare event the agents can plan into; display fields start neutral.

        Slugs stay pretty because frontend routes key on them; a name collision gets
        the same uuid suffix idiom create_approval uses.
        """
        event_id = _slugify(name)
        if self.db.get(orm.Event, event_id) is not None:
            event_id = f"{event_id}-{uuid4().hex[:6]}"
        event = orm.Event(
            id=event_id,
            kind=kind,
            name=name,
            short_name=name,
            status_label="Planning",
            date=date,
            location=location,
            headcount=headcount,
            days_to_go="TBD",
            percent_complete=0,
            total_usd=0,
            paid_usd=0,
            pending_usd=0,
            vendors_confirmed=0,
            vendors_total=0,
            vendors_in_progress=0,
            auto_approve_limit="$500",  # the seed's default; the approvals UI can change it
            savings_footnote="",
        )
        self.db.add(event)
        self.db.commit()
        return web.EventOverview.model_validate(event)

    def save_plan(
        self,
        event_id: str,
        plan: EventPlan,
        *,
        requirements: EventRequirements | None = None,
        budget_review: BudgetReview | None = None,
        today: date | None = None,
    ) -> None:
        """Replace this event's plan/budget/risk rows with ones derived from `plan`.

        The planning modules turn the pipeline's EventPlan (optionally enriched by the
        budget agent's review) into ORM rows; this writes them as one transaction, clearing
        the prior plan first so re-planning is idempotent. The event row must already exist
        — its plan children foreign-key to it. Imported here, not at module top, so serving
        the read-only dashboard never loads the agent/workflow stack.
        """
        from planning.budget_optimizer import BudgetOptimizer
        from planning.constraints import PlanningConstraints, parse_iso_date
        from planning.risk_analyzer import RiskAnalyzer
        from planning.schedule_optimizer import ScheduleOptimizer
        from planning.task_graph import TaskGraph

        today = today or date.today()
        constraints = PlanningConstraints.from_requirements(requirements)
        graph = TaskGraph.from_plan(plan)
        budget = BudgetOptimizer(plan, constraints=constraints, review=budget_review).build(event_id)
        risks = RiskAnalyzer(
            plan,
            constraints=constraints,
            today=today,
            over_budget_usd=budget.over_budget_usd,
            budget_review=budget_review,
        ).rows(event_id)
        schedule = ScheduleOptimizer(plan)
        milestones = schedule.rows(event_id, today=today)
        deadlines = schedule.deadline_rows(event_id)

        self._clear_plan(event_id)
        for phase in graph.phase_rows(event_id):
            self.db.add(phase)
        for group in graph.group_rows(event_id):
            group_row = orm.PlanTaskGroup(
                event_id=event_id, name=group.name, owner=group.owner, tone=group.tone, ordinal=group.ordinal
            )
            self.db.add(group_row)
            self.db.flush()  # assign group_row.id before its tasks reference it
            for task in group.tasks:
                task.group_id = group_row.id
                self.db.add(task)
        for row in (*risks, *milestones, *deadlines, *budget.categories, *budget.savings):
            self.db.add(row)

        event = self.db.get(orm.Event, event_id)
        if event is not None:
            event.total_usd = budget.total_usd
            event.paid_usd = budget.paid_usd
            event.pending_usd = budget.pending_usd
            event.percent_complete = graph.percent_complete()
            event.savings_footnote = budget.footnote
            # The requirements date wins when it parses; the plan's resolved date covers
            # briefs like "July 30" that never carried a year. Past dates keep "TBD".
            event_date = constraints.event_date or parse_iso_date(plan.event_date)
            if event_date is not None and event_date >= today:
                event.days_to_go = f"{(event_date - today).days} days"
        self.db.commit()

    def save_vendors(self, event_id: str, shortlist: VendorShortlist) -> None:
        """Replace this event's vendor rows with the sourcing shortlist, counters included.

        Delete-and-rewrite mirrors save_plan so re-sourcing is idempotent. Status stays
        within the web app's closed vocabulary: the top pick per category awaits the
        user's decision, alternates read as still sourcing — research alone confirms
        nothing, and quotes only arrive with outreach.
        """
        self.db.execute(delete(orm.Vendor).where(orm.Vendor.event_id == event_id))
        ordered = sorted(shortlist.candidates, key=lambda c: (c.category, c.rank))
        for ordinal, candidate in enumerate(ordered):
            self.db.add(
                orm.Vendor(
                    id=f"vendor-{event_id}-{ordinal}-{_slugify(candidate.name)}",
                    event_id=event_id,
                    initials=_initials(candidate.name),
                    name=candidate.name,
                    category=candidate.category.capitalize(),
                    status="Awaiting you" if candidate.rank == 1 else "Sourcing",
                    quotes=0,
                    last_activity="just now",
                    cost=_cost_label(candidate.price_notes),
                    ordinal=ordinal,
                )
            )
        self._refresh_vendor_counters(event_id)
        self.db.commit()

    def confirm_vendor(
        self,
        event_id: str,
        *,
        name: str,
        category: str | None = None,
        amount_usd: float | None = None,
        price_notes: str | None = None,
    ) -> None:
        """Flip the booked vendor's row to Confirmed and refresh the overview counters.

        A booking can run off a memory shortlist that predates vendor persistence, so a
        missing row is created rather than dropped. The cost turns firm (no ~ estimate
        marker): the approved amount when known, else the first price in the notes.
        """
        row = self.db.scalar(
            select(orm.Vendor).where(
                orm.Vendor.event_id == event_id, func.lower(orm.Vendor.name) == name.lower()
            )
        )
        if row is None:
            next_ordinal = self.db.scalar(
                select(func.coalesce(func.max(orm.Vendor.ordinal), -1)).where(orm.Vendor.event_id == event_id)
            ) + 1
            row = orm.Vendor(
                id=f"vendor-{event_id}-{next_ordinal}-{_slugify(name)}",
                event_id=event_id,
                initials=_initials(name),
                name=name,
                category=(category or "Vendor").capitalize(),
                status="Confirmed",
                quotes=0,
                last_activity="just now",
                cost="—",
                ordinal=next_ordinal,
            )
            self.db.add(row)
        row.status = "Confirmed"
        row.last_activity = "just now"
        if amount_usd is not None:
            row.cost = f"${amount_usd:,.0f}"
        else:
            match = _PRICE.search(price_notes or "")
            if match:
                row.cost = match.group(0)
        self._refresh_vendor_counters(event_id)
        self.db.commit()

    def save_outreach(self, event_id: str, *, contacted: list[str], comparison: QuoteComparison | None) -> None:
        """Advance vendor rows after an outreach round: successfully contacted vendors
        read as negotiating, and the comparison's quotes land as counts and costs.

        Statuses only move forward here — a Confirmed row never regresses. Vendors
        without a row are skipped: creating rows belongs to sourcing, and outreach can
        run off a memory shortlist that predates vendor persistence.
        """
        by_name = {
            row.name.lower(): row for row in self._ordered(orm.Vendor, orm.Vendor.event_id == event_id)
        }
        for name in contacted:
            row = by_name.get(name.lower())
            if row is None:
                continue
            if row.status != "Confirmed":
                row.status = "Negotiating"
            row.last_activity = "just now"
        for quote in (comparison.quotes if comparison is not None else []):
            row = by_name.get(quote.vendor_name.lower())
            if row is None or quote.quoted_total_usd is None:
                continue
            # One QuoteStatus is a thread's current state, so it counts as one quote on
            # hand; max() keeps any higher count a richer source already recorded.
            row.quotes = max(row.quotes, 1)
            row.cost = f"${quote.quoted_total_usd:,.0f}"  # a real quote reads firm, no ~ marker
            row.last_activity = "just now"
        self.db.commit()

    def _refresh_vendor_counters(self, event_id: str) -> None:
        # Recomputed from the rows (pending ones included via flush) so every writer
        # agrees: in-progress is simply everyone not yet confirmed.
        event = self.db.get(orm.Event, event_id)
        if event is None:
            return
        self.db.flush()
        total = self.db.scalar(select(func.count()).where(orm.Vendor.event_id == event_id)) or 0
        confirmed = (
            self.db.scalar(
                select(func.count()).where(orm.Vendor.event_id == event_id, orm.Vendor.status == "Confirmed")
            )
            or 0
        )
        event.vendors_total = total
        event.vendors_confirmed = confirmed
        event.vendors_in_progress = total - confirmed

    def create_approval(
        self,
        *,
        event_id: str,
        kind: str,
        agent: str,
        agent_tone: str,
        tag: str,
        title: str,
        description: str,
        amount: str,
        vendor: str,
        thread_id: str | None = None,
        action: dict | None = None,
    ) -> web.ApprovalItem:
        # New row leads the pending list; a matching feed line mirrors resolve_approval.
        agent_name = _AGENT_SUFFIX.sub("", agent)
        approval = orm.Approval(
            id=f"approval-{_slugify(title)}-{uuid4().hex[:6]}",
            event_id=event_id,
            kind=kind,
            agent=agent,
            agent_tone=agent_tone,
            tag=tag,
            title=title,
            description=description,
            amount=amount,
            vendor=vendor,
            thread_id=thread_id,
            resolved=False,
            ordinal=self._lead_ordinal(orm.Approval, orm.Approval.event_id == event_id),
            action=action,
        )
        activity = orm.ActivityItem(
            id=f"activity-{approval.id}",
            event_id=event_id,
            agent=agent_name,
            tone="amber",
            time_ago="just now",
            description=f"{agent_name} flagged {title} — {amount} for your approval.",
            pool=False,
            ordinal=self._lead_ordinal(
                orm.ActivityItem,
                orm.ActivityItem.event_id == event_id,
                orm.ActivityItem.pool.is_(False),
            ),
        )
        self.db.add(approval)
        self.db.add(activity)
        self.db.commit()
        return web.ApprovalItem.model_validate(approval)

    def resolve_approval(self, approval_id: str, approved: bool) -> web.DecisionRecord | None:
        approval = self.db.get(orm.Approval, approval_id)
        if approval is None or approval.resolved:
            return None

        approval.resolved = True
        agent_name = _AGENT_SUFFIX.sub("", approval.agent)
        if approved:
            line = f"You approved {approval.title} — {approval.amount}. The {agent_name} agent is proceeding now."
        else:
            line = f"You declined {approval.title}. The {agent_name} agent will source an alternative."

        decision = orm.DecisionRecord(
            id=f"decision-{approval.id}",
            event_id=approval.event_id,
            title=approval.title,
            amount=approval.amount,
            when="just now",
            approved=approved,
            ordinal=self._lead_ordinal(orm.DecisionRecord, orm.DecisionRecord.event_id == approval.event_id),
        )
        activity = orm.ActivityItem(
            # Prefixed distinctly: create_approval already owns "activity-{approval.id}".
            id=f"activity-decision-{approval.id}",
            event_id=approval.event_id,
            agent=agent_name,
            tone="green" if approved else "amber",
            time_ago="just now",
            description=line,
            pool=False,
            ordinal=self._lead_ordinal(
                orm.ActivityItem,
                orm.ActivityItem.event_id == approval.event_id,
                orm.ActivityItem.pool.is_(False),
            ),
        )
        self.db.add(decision)
        self.db.add(activity)
        self.db.commit()
        return web.DecisionRecord.model_validate(decision)

    def add_activity(self, event_id: str, *, agent: str, tone: str, description: str) -> None:
        """One feed line, leading the rail — how background runs narrate themselves."""
        self.db.add(
            orm.ActivityItem(
                id=f"activity-{uuid4().hex[:10]}",
                event_id=event_id,
                agent=agent,
                tone=tone,
                time_ago="just now",
                description=description,
                pool=False,
                ordinal=self._lead_ordinal(
                    orm.ActivityItem,
                    orm.ActivityItem.event_id == event_id,
                    orm.ActivityItem.pool.is_(False),
                ),
            )
        )
        self.db.commit()

    def toggle_rule(self, event_id: str, rule_id: str) -> web.SpendingRule | None:
        rule = self.db.get(orm.SpendingRule, rule_id)
        if rule is None or rule.event_id != event_id:
            return None
        rule.value = "Ask first" if rule.value == "Auto" else "Auto"
        self.db.commit()
        return web.SpendingRule.model_validate(rule)

    def set_auto_approve_limit(self, event_id: str, limit: str) -> str | None:
        event = self.db.get(orm.Event, event_id)
        if event is None:
            return None
        event.auto_approve_limit = limit
        self.db.commit()
        return event.auto_approve_limit

    def update_event(
        self,
        event_id: str,
        *,
        name: str | None = None,
        kind: str | None = None,
        date: str | None = None,
        location: str | None = None,
        headcount: str | None = None,
    ) -> web.EventOverview | None:
        """Patch the user-editable event descriptors; only provided fields change."""
        event = self.db.get(orm.Event, event_id)
        if event is None:
            return None
        if name is not None:
            # short_name is the sidebar label; create_event seeds it from name, so keep them together.
            event.name = name
            event.short_name = name
        if kind is not None:
            event.kind = kind
        if date is not None:
            event.date = date
        if location is not None:
            event.location = location
        if headcount is not None:
            event.headcount = headcount
        self.db.commit()
        return web.EventOverview.model_validate(event)

    # ---- Helpers ----

    def _ordered(self, model, *conditions):
        stmt = select(model).where(*conditions).order_by(model.ordinal)
        return list(self.db.scalars(stmt).all())

    def _resolve_demo(self, event_id: str) -> str:
        """Demo override: an event flagged at intake reads a curated fixture event's rows,
        so 'cake'/'pizza' prompts render a fixed dashboard regardless of live output. Falls
        back to the real event when nothing is flagged or the fixture isn't seeded."""
        row = self.db.get(orm.EventMemoryRow, (event_id, DEMO_FIXTURE))
        if row is None:
            return event_id
        return row.value if self.db.get(orm.Event, row.value) is not None else event_id

    def _clear_plan(self, event_id: str) -> None:
        # Drop the whole plan/budget/risk set for this event; deleting the task groups
        # cascades to their tasks at the database level.
        for model in (
            orm.PlanPhase,
            orm.PlanTaskGroup,
            orm.RiskItem,
            orm.Milestone,
            orm.BudgetCategory,
            orm.SavingSuggestion,
        ):
            self.db.execute(delete(model).where(model.event_id == event_id))
        # Only the plan-owned 'key' list; 'agenda' rows belong to the calendar surface.
        self.db.execute(
            delete(orm.DeadlineItem).where(
                orm.DeadlineItem.event_id == event_id, orm.DeadlineItem.list_kind == "key"
            )
        )

    def _deadlines(self, event_id: str, list_kind: str) -> list[web.DeadlineItem]:
        event_id = self._resolve_demo(event_id)
        rows = self._ordered(
            orm.DeadlineItem,
            orm.DeadlineItem.event_id == event_id,
            orm.DeadlineItem.list_kind == list_kind,
        )
        return [web.DeadlineItem.model_validate(d) for d in rows]

    def _lead_ordinal(self, model, *conditions) -> int:
        # New rows lead their list: one below the current minimum (lists read ASC).
        current_min = self.db.scalar(select(func.min(model.ordinal)).where(*conditions))
        return (current_min if current_min is not None else 0) - 1
