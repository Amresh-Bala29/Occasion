"""Event routes: the read API the dashboard fetches, plus a couple of settings writes.

Reads are event-scoped (`/events/{event_id}/…`) and map one-to-one to the web app's
lib/api.ts getters. Handlers are sync `def` so FastAPI runs the blocking repository
calls in its threadpool. `response_model_exclude_none` keeps optional fields absent
(not null) so the JSON matches the mock exactly.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_event_repository, get_run_manager, get_supervisor
from approvals.approval_manager import ApprovalManager, ProposedAction
from approvals.sensitive_actions import ActionCategory
from core.runs import RunManager
from core.supervisor import EventSessionsReport, Supervisor
from database.repositories.event_repository import EventRepository
from models import web
from workflows.event_planning import VendorCategory

router = APIRouter()


class AutoApproveLimitBody(BaseModel):
    limit: str


class CreateEventBody(BaseModel):
    name: str
    kind: str = "Event"
    date: str = "TBD"
    location: str = "TBD"
    headcount: str = "TBD"


class BookingProposalBody(BaseModel):
    """A vendor booking someone (or some agent) wants to make, pre-policy."""

    vendor_name: str
    url: str
    category: VendorCategory
    amount_usd: float = 0.0
    description: str = ""
    availability: str | None = None
    price_notes: str | None = None
    budget_cap_usd: float | None = None


class BookingProposalResult(BaseModel):
    """Where the proposal landed: executing now, or parked as a pending approval."""

    status: str  # executing | pending_approval
    reason: str
    run_id: str | None = None
    approval_id: str | None = None


@router.get("", response_model=list[web.EventOverview], response_model_exclude_none=True)
def list_events(repo: EventRepository = Depends(get_event_repository)) -> list[web.EventOverview]:
    return repo.list_events()


@router.post("", response_model=web.EventOverview)
def create_event(body: CreateEventBody, repo: EventRepository = Depends(get_event_repository)) -> web.EventOverview:
    return repo.create_event(
        name=body.name, kind=body.kind, date=body.date, location=body.location, headcount=body.headcount
    )


@router.get("/{event_id}/dashboard", response_model=web.DashboardData, response_model_exclude_none=True)
def get_dashboard(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> web.DashboardData:
    dashboard = repo.get_dashboard(event_id)
    if dashboard is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id!r} not found")
    return dashboard


@router.get("/{event_id}/vendors", response_model=list[web.Vendor], response_model_exclude_none=True)
def get_vendors(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> list[web.Vendor]:
    return repo.get_vendors(event_id)


@router.get("/{event_id}/plan", response_model=web.EventPlan, response_model_exclude_none=True)
def get_plan(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> web.EventPlan:
    return repo.get_plan(event_id)


@router.get("/{event_id}/budget", response_model=web.BudgetDetail, response_model_exclude_none=True)
def get_budget(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> web.BudgetDetail:
    return repo.get_budget(event_id)


@router.get("/{event_id}/calendar", response_model=list[web.CalendarEventItem], response_model_exclude_none=True)
def get_calendar(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> list[web.CalendarEventItem]:
    return repo.get_calendar_events(event_id)


@router.get("/{event_id}/agenda", response_model=list[web.DeadlineItem], response_model_exclude_none=True)
def get_agenda(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> list[web.DeadlineItem]:
    return repo.get_agenda(event_id)


@router.get("/{event_id}/deadlines", response_model=list[web.DeadlineItem], response_model_exclude_none=True)
def get_key_deadlines(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> list[web.DeadlineItem]:
    return repo.get_key_deadlines(event_id)


@router.get("/{event_id}/conversations", response_model=list[web.Conversation], response_model_exclude_none=True)
def get_conversations(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> list[web.Conversation]:
    return repo.get_conversations(event_id)


@router.get("/{event_id}/decisions", response_model=list[web.DecisionRecord], response_model_exclude_none=True)
def get_decisions(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> list[web.DecisionRecord]:
    return repo.get_decisions(event_id)


@router.get("/{event_id}/spending-rules", response_model=list[web.SpendingRule], response_model_exclude_none=True)
def get_spending_rules(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> list[web.SpendingRule]:
    return repo.get_spending_rules(event_id)


@router.get("/{event_id}/post-event-tasks", response_model=list[web.PostEventTask], response_model_exclude_none=True)
def get_post_event_tasks(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> list[web.PostEventTask]:
    return repo.get_post_event_tasks(event_id)


@router.get("/{event_id}/activity-pool", response_model=list[web.ActivityItem], response_model_exclude_none=True)
def get_activity_pool(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> list[web.ActivityItem]:
    return repo.get_activity_pool(event_id)


@router.get("/{event_id}/activity", response_model=list[web.ActivityItem], response_model_exclude_none=True)
def get_activity(event_id: str, repo: EventRepository = Depends(get_event_repository)) -> list[web.ActivityItem]:
    """The real feed — what agents actually did — newest first; the rail polls this."""
    return repo.get_activity(event_id)


@router.post("/{event_id}/spending-rules/{rule_id}", response_model=web.SpendingRule)
def toggle_spending_rule(
    event_id: str, rule_id: str, repo: EventRepository = Depends(get_event_repository)
) -> web.SpendingRule:
    rule = repo.toggle_rule(event_id, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Spending rule {rule_id!r} not found")
    return rule


@router.put("/{event_id}/auto-approve-limit")
def set_auto_approve_limit(
    event_id: str, body: AutoApproveLimitBody, repo: EventRepository = Depends(get_event_repository)
) -> dict:
    value = repo.set_auto_approve_limit(event_id, body.limit)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id!r} not found")
    return {"autoApproveLimit": value}


@router.post("/{event_id}/bookings", response_model=BookingProposalResult, response_model_exclude_none=True)
def propose_booking(
    event_id: str,
    body: BookingProposalBody,
    repo: EventRepository = Depends(get_event_repository),
    runs: RunManager = Depends(get_run_manager),
) -> BookingProposalResult:
    """The propose → approve → execute loop's entry point.

    The spending policy decides on the spot: within the user's auto-approve rules
    the booking executes immediately as a background run; otherwise it becomes a
    pending approval carrying the action, and approving it in the dashboard
    executes the same way. Either path lands in the activity rail.
    """
    action = {
        "type": "book_vendor",
        "event_id": event_id,
        "candidate": {
            "name": body.vendor_name,
            "url": body.url,
            "category": body.category,
            "availability": body.availability,
            "price_notes": body.price_notes,
        },
        "budget_cap_usd": body.budget_cap_usd,
    }
    decision = ApprovalManager(repo).review(
        ProposedAction(
            event_id=event_id,
            agent="Purchasing agent",
            category=ActionCategory.DEPOSIT,
            title=f"Book {body.vendor_name}",
            description=body.description or f"Booking {body.vendor_name} ({body.category}).",
            vendor=body.vendor_name,
            amount_usd=body.amount_usd,
            action=action,
        )
    )
    if decision.requires_approval:
        return BookingProposalResult(
            status="pending_approval", reason=decision.reason, approval_id=decision.approval_id
        )
    record = runs.start_booking(action, approval_note=f"Auto-approved by your spending rules: {decision.reason}")
    return BookingProposalResult(status="executing", reason=decision.reason, run_id=record.id)


@router.get("/{event_id}/agent-sessions", response_model=EventSessionsReport, response_model_exclude_none=True)
def get_agent_sessions(event_id: str, supervisor: Supervisor = Depends(get_supervisor)) -> EventSessionsReport:
    """Live H sessions for this event plus the account's session-slot quota.

    Always 200 with an honest report: no live sessions is an empty list (group_id
    scoping needs no DB), and a missing key or H failure is succeeded=False, not a raise.
    """
    return supervisor.event_sessions(event_id)
