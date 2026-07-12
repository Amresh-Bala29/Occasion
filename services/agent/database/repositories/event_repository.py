"""Data access for the event workspace.

One repository owns the whole `events` aggregate: a read method per web-app getter,
plus the three writes the approvals UI needs. Reads return the Pydantic response
models from models/web.py, ordered by each row's `ordinal` so the exact mock order is
restored. The composite dashboard stores its headline figures verbatim and computes
only the two that genuinely reconcile — `agentsWorking` and `messagesCount`.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import models as orm
from models import web

# "Purchasing agent" -> "Purchasing" for the decision/activity copy, matching the client.
_AGENT_SUFFIX = re.compile(r" agent$", re.IGNORECASE)


class EventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- Reads ----

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

    def get_post_event_tasks(self, event_id: str) -> list[web.PostEventTask]:
        rows = self._ordered(orm.PostEventTask, orm.PostEventTask.event_id == event_id)
        return [web.PostEventTask.model_validate(t) for t in rows]

    def get_activity_pool(self, event_id: str) -> list[web.ActivityItem]:
        rows = self._ordered(
            orm.ActivityItem, orm.ActivityItem.event_id == event_id, orm.ActivityItem.pool.is_(True)
        )
        return [web.ActivityItem.model_validate(a) for a in rows]

    # ---- Writes ----

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
            id=f"activity-{approval.id}",
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
