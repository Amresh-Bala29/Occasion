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
from models import web

if TYPE_CHECKING:
    from agents.budget_agent import BudgetReview
    from agents.requirements_agent import EventRequirements
    from workflows.event_planning import EventPlan

# "Purchasing agent" -> "Purchasing" for the decision/activity copy, matching the client.
_AGENT_SUFFIX = re.compile(r" agent$", re.IGNORECASE)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())[:40].strip("-")
    return slug or "action"


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
        event = self.db.get(orm.Event, event_id)
        if event is None:
            return None

        approvals = self._ordered(
            orm.Approval, orm.Approval.event_id == event_id, orm.Approval.resolved.is_(False)
        )
        agents = self._ordered(orm.AgentStatusRow, orm.AgentStatusRow.event_id == event_id)
        activity = self._ordered(
            orm.ActivityItem, orm.ActivityItem.event_id == event_id, orm.ActivityItem.pool.is_(False)
        )
        messages_count = self.db.scalar(
            select(func.count())
            .select_from(orm.Conversation)
            .where(
                orm.Conversation.event_id == event_id,
                orm.Conversation.unread.is_(True),
                orm.Conversation.archived.is_(False),
            )
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
            agents_working=len(agents),
            messages_count=messages_count or 0,
            auto_approve_limit=event.auto_approve_limit,
        )

    def get_vendors(self, event_id: str) -> list[web.Vendor]:
        rows = self._ordered(orm.Vendor, orm.Vendor.event_id == event_id)
        return [web.Vendor.model_validate(v) for v in rows]

    def get_plan(self, event_id: str) -> web.EventPlan:
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
        categories = self._ordered(orm.BudgetCategory, orm.BudgetCategory.event_id == event_id)
        savings = self._ordered(orm.SavingSuggestion, orm.SavingSuggestion.event_id == event_id)
        event = self.db.get(orm.Event, event_id)
        return web.BudgetDetail(
            categories=[web.BudgetCategory.model_validate(c) for c in categories],
            savings=[web.SavingSuggestion.model_validate(s) for s in savings],
            savings_footnote=event.savings_footnote if event else "",
        )

    def get_calendar_events(self, event_id: str) -> list[web.CalendarEventItem]:
        rows = self._ordered(orm.CalendarEvent, orm.CalendarEvent.event_id == event_id)
        return [web.CalendarEventItem.model_validate(c) for c in rows]

    def get_agenda(self, event_id: str) -> list[web.DeadlineItem]:
        return self._deadlines(event_id, "agenda")

    def get_key_deadlines(self, event_id: str) -> list[web.DeadlineItem]:
        return self._deadlines(event_id, "key")

    def get_conversations(self, event_id: str) -> list[web.Conversation]:
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
        rows = self._ordered(orm.DecisionRecord, orm.DecisionRecord.event_id == event_id)
        return [web.DecisionRecord.model_validate(d) for d in rows]

    def get_spending_rules(self, event_id: str) -> list[web.SpendingRule]:
        rows = self._ordered(orm.SpendingRule, orm.SpendingRule.event_id == event_id)
        return [web.SpendingRule.model_validate(r) for r in rows]

    def get_auto_approve_limit(self, event_id: str) -> str | None:
        event = self.db.get(orm.Event, event_id)
        return event.auto_approve_limit if event else None

    def get_post_event_tasks(self, event_id: str) -> list[web.PostEventTask]:
        rows = self._ordered(orm.PostEventTask, orm.PostEventTask.event_id == event_id)
        return [web.PostEventTask.model_validate(t) for t in rows]

    def get_activity_pool(self, event_id: str) -> list[web.ActivityItem]:
        rows = self._ordered(
            orm.ActivityItem, orm.ActivityItem.event_id == event_id, orm.ActivityItem.pool.is_(True)
        )
        return [web.ActivityItem.model_validate(a) for a in rows]

    def get_activity(self, event_id: str) -> list[web.ActivityItem]:
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
        from planning.constraints import PlanningConstraints
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
        milestones = ScheduleOptimizer(plan).rows(event_id, today=today)

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
        for row in (*risks, *milestones, *budget.categories, *budget.savings):
            self.db.add(row)

        event = self.db.get(orm.Event, event_id)
        if event is not None:
            event.total_usd = budget.total_usd
            event.paid_usd = budget.paid_usd
            event.pending_usd = budget.pending_usd
            event.percent_complete = graph.percent_complete()
            event.savings_footnote = budget.footnote
        self.db.commit()

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

    # ---- Helpers ----

    def _ordered(self, model, *conditions):
        stmt = select(model).where(*conditions).order_by(model.ordinal)
        return list(self.db.scalars(stmt).all())

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

    def _deadlines(self, event_id: str, list_kind: str) -> list[web.DeadlineItem]:
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
