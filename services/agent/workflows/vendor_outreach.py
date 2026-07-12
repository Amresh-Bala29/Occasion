"""Vendor outreach, quoting, and negotiation workflow.

Contacts shortlisted vendors and tracks what comes back:

1. Code picks the best-ranked candidates per category.
2. A deep Holo completion drafts a personalized inquiry per vendor (with a plain
   template as fallback), so the browser agent sends exact, pre-composed copy.
3. H's general web agent sends each message — inquiry form when one exists,
   signed-in Gmail otherwise — in parallel waves of three.
4. A deep Holo completion turns the send reports into a quote comparison with
   escalations: the decisions only the user can make.

Sends go to the general web agent rather than the domain agents deliberately: each
domain agent is locked to its research answer schema, so a send confirmation would
fail validation after the email had already gone out — an unrepeatable action
reading as a retryable failure. `follow_up` chases silent vendors, checking the
thread before nudging so a reply is never double-nudged; `negotiate` sends one
propose-only counter-message. Accepting and booking stay behind
VendorSourcingWorkflow.book's approval gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, Field

from core.orchestrator import Orchestrator, TaskRun
from integrations.h_company.client import HClient
from integrations.h_company.schemas import DEFAULT_AGENT, SessionResult
from memory.vector_store import vendor_scope
from memory.vendor_memory import vendor_key_for
from models.task import Task
from workflows.event_planning import EventPlan, complete, slug, structured
from workflows.vendor_sourcing import VendorCandidate, VendorShortlist

if TYPE_CHECKING:
    from core.state import Memory


class OutreachDraft(BaseModel):
    """One vendor-ready message; `vendor_name` joins it back to its candidate."""

    vendor_name: str
    subject: str
    message: str
    questions: list[str] = []


class OutreachDrafts(BaseModel):
    """The drafting completion's structured answer."""

    drafts: list[OutreachDraft] = []


class QuoteStatus(BaseModel):
    """Where one vendor thread stands."""

    vendor_name: str
    category: str
    contacted: bool
    channel: str | None = Field(None, description="email | form | blocked | failed")
    quote_summary: str | None = None
    quoted_total_usd: float | None = None
    terms_notes: str | None = Field(None, description="Deposit, cancellation, and quote-validity terms as stated.")
    awaiting_reply: bool = True
    issues: list[str] = []


class Escalation(BaseModel):
    """A decision only the user can make, phrased as the question to answer."""

    decision: str
    context: str
    urgency: str | None = None


class QuoteComparison(BaseModel):
    """The comparison completion's structured answer."""

    quotes: list[QuoteStatus] = []
    comparison: str | None = Field(None, description="Cross-vendor comparison, only over vendors with real quotes.")
    recommendations: list[str] = []
    escalations: list[Escalation] = []
    follow_ups_needed: list[str] = Field(default=[], description="Vendors who are silent or blocked and worth chasing.")


class NegotiationRound(BaseModel):
    """One negotiation exchange: what was sent and how the send went."""

    vendor_name: str
    draft_run: SessionResult | None = None
    message: str
    send_run: TaskRun


class OutreachReport(BaseModel):
    """Everything one outreach round produced.

    candidates, drafts, send_tasks, and send_runs align by index, so each vendor's
    exact message, prompt, and result read straight across.
    """

    event_id: str
    candidates: list[VendorCandidate] = []
    drafts_run: SessionResult | None = None
    drafts: list[OutreachDraft] = []
    send_tasks: list[Task] = []
    send_runs: list[TaskRun] = []
    comparison_run: SessionResult | None = None
    comparison: QuoteComparison | None = None
    succeeded: bool = False


DRAFT_INSTRUCTIONS = """\
You draft vendor inquiry messages for an event coordinator. Produce one draft per
vendor named in the prompt, with vendor_name copied exactly.

Each message:
- Professional and concise; state the event's date, headcount, and the needs
  relevant to this vendor's category.
- Ask for: availability confirmation for the date, an itemized quote for the
  stated headcount, what the price includes, and deposit and cancellation terms.
- Fold in any vendor-specific concerns from the prompt as questions.
- Request a reply within a few business days.
- No commitment language — this is an inquiry, not an acceptance.
- Do not invent names or contact details; sign off generically as the event
  coordination team (the signed-in email account supplies identity)."""

NUDGE_INSTRUCTIONS = """\
You draft short follow-up notes to vendors who have not answered an earlier
inquiry. Produce one draft per vendor named in the prompt, with vendor_name copied
exactly and subject reusing the original subject so the reply stays in its thread.

Each note is two or three sentences: reference the original request, restate the
one thing needed (availability and an itemized quote), and give a reply-by date
framed by the event date. Courteous, no pressure tactics, no commitment language."""

NEGOTIATE_INSTRUCTIONS = """\
You draft one negotiation reply to a vendor for an event coordinator, with
vendor_name copied exactly and subject reusing the original thread's subject.

Acknowledge the vendor's quote as reported, then make the coordinator's ask
plainly and courteously, as a question. Propose only — no accepting counter-offers
and no commitment language."""

COMPARE_INSTRUCTIONS = """\
You track vendor outreach for an event coordinator: who was contacted, what came
back, and what needs the user's decision.

Rules:
- One quote status per vendor in the prompt, with vendor_name copied exactly.
- contacted and channel reflect what the send report actually says; a SEND FAILED
  vendor was not contacted, and the failure goes in its issues.
- Record quoted figures only when a number was actually stated, normalized into
  quoted_total_usd. Everything without a real reply stays awaiting_reply.
- The comparison covers only vendors with real quotes.
- escalations are decisions carrying money, contract, or material tradeoff weight —
  phrase each as the exact question the user must answer.
- follow_ups_needed lists vendors who are silent or blocked and worth chasing.
- When a prior comparison is included, carry its knowledge forward and update it
  with the new reports."""


class VendorOutreachWorkflow:
    """Sequential outreach pipeline: select -> draft -> send -> compare.

    A failed draft stage falls back to a deterministic template — an inquiry built
    from real facts is strictly better than no outreach. Failed sends flow into the
    comparison as explicit gaps. Nothing raises on agent failure.
    """

    def __init__(
        self,
        client: HClient | None = None,
        http_client: httpx.Client | None = None,
        *,
        memory: Memory | None = None,
    ) -> None:
        self._orchestrator = Orchestrator(client=client, http_client=http_client, memory=memory)
        self._memory = memory
        self._http = http_client

    async def run(
        self,
        shortlist: VendorShortlist,
        *,
        event_id: str,
        plan: EventPlan | None = None,
        max_per_category: int = 2,
    ) -> OutreachReport:
        """Request quotes from the shortlist's best candidates per category."""
        candidates = self._select(shortlist, max_per_category)
        report = OutreachReport(event_id=event_id, candidates=candidates)
        if not candidates:
            return report  # nothing to contact, nothing to compare
        context = _event_context(plan)
        report.drafts_run, report.drafts = await self._draft(candidates, context)
        report.send_tasks = self._send_tasks(candidates, report.drafts, event_id)
        report.send_runs = await self._orchestrator.run_tasks(report.send_tasks)
        self._remember_contacts(candidates, report.send_runs, event_id)
        report.comparison_run = await self._compare(candidates, report.drafts, report.send_runs, prior=None)
        report.comparison = structured(report.comparison_run, QuoteComparison)
        if report.comparison is not None:
            self._remember_quotes(report.comparison, candidates, event_id)
        # Outreach that reached nobody accomplished nothing, however tidy the report.
        report.succeeded = report.comparison is not None and any(run.result.succeeded for run in report.send_runs)
        return report

    async def follow_up(self, report: OutreachReport, *, event_id: str) -> OutreachReport:
        """Chase silent and failed vendors from a prior round.

        Each session reads the thread before writing: a vendor who replied gets
        their answer extracted, not another nudge. Takes the prior report as input
        because there is no persistence layer yet.
        """
        targets = self._follow_up_targets(report)
        next_report = OutreachReport(event_id=event_id, candidates=targets)
        if not targets:
            # Nobody to chase, so the prior picture is still the current one.
            next_report.comparison = report.comparison
            next_report.succeeded = report.comparison is not None
            return next_report
        subjects = _subjects_by_vendor(report)
        next_report.drafts_run, next_report.drafts = await self._draft_nudges(targets, subjects, report.comparison)
        next_report.send_tasks = [
            Task(
                id=f"{event_id}-followup-{slug(candidate.name)}",
                event_id=event_id,
                title=_render_follow_up_brief(candidate, subjects[candidate.name], nudge),
                assignee_agent=DEFAULT_AGENT,
            )
            for candidate, nudge in zip(targets, next_report.drafts)
        ]
        next_report.send_runs = await self._orchestrator.run_tasks(next_report.send_tasks)
        next_report.comparison_run = await self._compare(
            targets, next_report.drafts, next_report.send_runs, prior=report.comparison
        )
        next_report.comparison = structured(next_report.comparison_run, QuoteComparison)
        next_report.succeeded = next_report.comparison is not None and any(
            run.result.succeeded for run in next_report.send_runs
        )
        return next_report

    async def negotiate(self, report: OutreachReport, vendor_name: str, *, event_id: str, ask: str) -> NegotiationRound:
        """Send one propose-only counter-message in an existing vendor thread."""
        candidate = next((c for c in report.candidates if c.name == vendor_name), None)
        if candidate is None:
            raise ValueError(f"unknown vendor {vendor_name!r}; negotiation targets a vendor from this report")
        subject = _subjects_by_vendor(report)[vendor_name]
        draft_run = await self._draft_counter(candidate, subject, report.comparison, ask)
        drafted = structured(draft_run, OutreachDraft)
        if drafted is None:
            drafted = OutreachDraft(vendor_name=vendor_name, subject=subject, message=_generic_counter(candidate, ask))
        task = Task(
            id=f"{event_id}-negotiate-{slug(vendor_name)}",
            event_id=event_id,
            title=_render_reply_brief(candidate, subject, drafted.message),
            assignee_agent=DEFAULT_AGENT,
        )
        send_run = await self._orchestrator.run_task(task)
        return NegotiationRound(vendor_name=vendor_name, draft_run=draft_run, message=drafted.message, send_run=send_run)

    def _select(self, shortlist: VendorShortlist, max_per_category: int) -> list[VendorCandidate]:
        """The best-ranked candidates per category — at least two where available,
        because a single quote can't be compared."""
        by_category: dict[str, list[VendorCandidate]] = {}
        for candidate in shortlist.candidates:
            by_category.setdefault(candidate.category, []).append(candidate)
        selected: list[VendorCandidate] = []
        for candidates in by_category.values():
            selected.extend(sorted(candidates, key=lambda candidate: candidate.rank)[:max_per_category])
        return selected

    async def _draft(self, candidates: list[VendorCandidate], context: str) -> tuple[SessionResult, list[OutreachDraft]]:
        blocks = [context]
        for candidate in candidates:
            details = [f"Vendor: {candidate.name} (category: {candidate.category}, site: {candidate.url})"]
            if candidate.price_notes:
                details.append(f"Known pricing: {candidate.price_notes}")
            if candidate.availability:
                details.append(f"Known availability: {candidate.availability}")
            if candidate.fit_rationale:
                details.append(f"Why shortlisted: {candidate.fit_rationale}")
            if candidate.concerns:
                details.append("Concerns to clarify: " + "; ".join(candidate.concerns))
            blocks.append("\n".join(details))
        run = await complete("\n\n".join(blocks), DRAFT_INSTRUCTIONS, OutreachDrafts, http_client=self._http)
        compiled = structured(run, OutreachDrafts)
        drafted = {draft.vendor_name: draft for draft in (compiled.drafts if compiled else [])}
        # Every candidate sends something: unmatched names fall back to the template.
        drafts = [drafted.get(candidate.name) or _generic_draft(candidate, context) for candidate in candidates]
        return run, drafts

    async def _draft_nudges(
        self,
        targets: list[VendorCandidate],
        subjects: dict[str, str],
        prior: QuoteComparison | None,
    ) -> tuple[SessionResult, list[OutreachDraft]]:
        statuses = {status.vendor_name: status for status in (prior.quotes if prior else [])}
        blocks = []
        for candidate in targets:
            lines = [
                f"Vendor: {candidate.name} (category: {candidate.category})",
                f"Original subject: {subjects[candidate.name]}",
            ]
            status = statuses.get(candidate.name)
            if status is not None:
                lines.append(f"Thread status: {status.model_dump_json()}")
            blocks.append("\n".join(lines))
        run = await complete("\n\n".join(blocks), NUDGE_INSTRUCTIONS, OutreachDrafts, http_client=self._http)
        compiled = structured(run, OutreachDrafts)
        drafted = {draft.vendor_name: draft for draft in (compiled.drafts if compiled else [])}
        nudges = [
            drafted.get(candidate.name) or _generic_nudge(candidate, subjects[candidate.name])
            for candidate in targets
        ]
        return run, nudges

    async def _draft_counter(
        self,
        candidate: VendorCandidate,
        subject: str,
        prior: QuoteComparison | None,
        ask: str,
    ) -> SessionResult:
        status = next(
            (status for status in (prior.quotes if prior else []) if status.vendor_name == candidate.name),
            None,
        )
        sections = [
            f"Vendor: {candidate.name} (category: {candidate.category})",
            f"Original subject: {subject}",
        ]
        if status is not None:
            sections.append(f"Their quote as reported: {status.model_dump_json()}")
        sections.append(f"The coordinator's ask: {ask}")
        return await complete("\n\n".join(sections), NEGOTIATE_INSTRUCTIONS, OutreachDraft, http_client=self._http)

    def _send_tasks(self, candidates: list[VendorCandidate], drafts: list[OutreachDraft], event_id: str) -> list[Task]:
        return [
            Task(
                id=f"{event_id}-outreach-{slug(candidate.name)}",
                event_id=event_id,
                title=_render_send_brief(candidate, draft),
                assignee_agent=DEFAULT_AGENT,
            )
            for candidate, draft in zip(candidates, drafts)
        ]

    async def _compare(
        self,
        candidates: list[VendorCandidate],
        drafts: list[OutreachDraft],
        runs: list[TaskRun],
        prior: QuoteComparison | None,
    ) -> SessionResult:
        blocks = []
        for candidate, draft, run in zip(candidates, drafts, runs):
            lines = [
                f"Vendor: {candidate.name} (category: {candidate.category})",
                f"Message sent:\nSubject: {draft.subject}\n{draft.message}",
            ]
            if run.result.succeeded:
                lines.append(f"Send run report:\n{run.result.answer or 'no report returned'}")
            else:
                # The failure must be model-visible so it lands in issues, not silence.
                lines.append(f"SEND FAILED: {run.result.error or run.result.status}")
            blocks.append("\n".join(lines))
        if prior is not None:
            blocks.append(f"Prior comparison (JSON):\n{prior.model_dump_json()}")
        return await complete("\n\n".join(blocks), COMPARE_INSTRUCTIONS, QuoteComparison, http_client=self._http)

    def _follow_up_targets(self, report: OutreachReport) -> list[VendorCandidate]:
        names = set(report.comparison.follow_ups_needed) if report.comparison else set()
        names.update(
            candidate.name
            for candidate, run in zip(report.candidates, report.send_runs)
            if not run.result.succeeded
        )
        return [candidate for candidate in report.candidates if candidate.name in names]

    def _remember_contacts(self, candidates: list[VendorCandidate], runs: list[TaskRun], event_id: str) -> None:
        """Record a contact for each vendor we reached, and file the send report as a
        vendor-scoped transcript for later recall."""
        if self._memory is None:
            return
        for candidate, run in zip(candidates, runs):
            if not run.result.succeeded:
                continue
            self._memory.vendors.record_contacted(candidate, event_id=event_id)
            if run.result.answer:
                self._memory.semantic.add_document(
                    run.result.answer,
                    scope=vendor_scope(vendor_key_for(candidate.name, candidate.url)),
                    kind="transcript",
                    event_id=event_id,
                )

    def _remember_quotes(self, comparison: QuoteComparison, candidates: list[VendorCandidate], event_id: str) -> None:
        """Record a quote for each vendor that returned a real number."""
        if self._memory is None:
            return
        by_name = {candidate.name: candidate for candidate in candidates}
        for quote in comparison.quotes:
            candidate = by_name.get(quote.vendor_name)
            if candidate is not None and quote.quoted_total_usd is not None:
                self._memory.vendors.record_quoted(candidate, total_usd=quote.quoted_total_usd, event_id=event_id)


def _event_context(plan: EventPlan | None) -> str:
    if plan is not None:
        return f"Event: {plan.event_summary}"
    return "Event: details are in each vendor's notes below."


def _subjects_by_vendor(report: OutreachReport) -> dict[str, str]:
    """Each vendor's thread subject — the Gmail search key for follow-ups and replies.

    Falls back to the template subject so a vendor whose draft was never recorded
    still resolves to the subject the template round would have used.
    """
    subjects = {draft.vendor_name: draft.subject for draft in report.drafts}
    for candidate in report.candidates:
        subjects.setdefault(candidate.name, f"Availability and quote request — {candidate.name}")
    return subjects


def _generic_draft(candidate: VendorCandidate, context: str) -> OutreachDraft:
    """Deterministic inquiry used when drafting fails; every fact in it is real."""
    return OutreachDraft(
        vendor_name=candidate.name,
        subject=f"Availability and quote request — {candidate.name}",
        message="\n".join(
            [
                f"Hello {candidate.name} team,",
                "",
                f"We are coordinating an upcoming event and are interested in your {candidate.category} services.",
                context,
                "",
                "Could you confirm your availability for our date and send an itemized quote for "
                "our headcount, including what the price covers and your deposit and cancellation terms?",
                "",
                "Thank you,",
                "The event coordination team",
            ]
        ),
    )


def _generic_nudge(candidate: VendorCandidate, original_subject: str) -> OutreachDraft:
    return OutreachDraft(
        vendor_name=candidate.name,
        subject=original_subject,
        message="\n".join(
            [
                f"Hello {candidate.name} team,",
                "",
                "Following up on our earlier inquiry — we are still interested and would "
                "appreciate your availability and an itemized quote when you have a moment.",
                "",
                "Thank you,",
                "The event coordination team",
            ]
        ),
    )


def _generic_counter(candidate: VendorCandidate, ask: str) -> str:
    return "\n".join(
        [
            f"Hello {candidate.name} team,",
            "",
            "Thank you for the quote. Before we decide, we wanted to ask:",
            ask,
            "",
            "We appreciate your consideration.",
            "The event coordination team",
        ]
    )


def _is_email(contact: str) -> bool:
    return "@" in contact and "://" not in contact


def _render_send_brief(candidate: VendorCandidate, draft: OutreachDraft) -> str:
    contact = candidate.contact_path or candidate.url
    if _is_email(contact):
        start = "https://mail.google.com"
        steps = [
            f"1. From the signed-in Gmail account, compose a new email to {contact}.",
            "2. Use exactly the subject and message below — do not rewrite them.",
            "3. Send it and confirm it appears in Sent mail.",
        ]
    else:
        start = contact
        found_how = (
            "Open the page and find the inquiry form or contact option."
            if candidate.contact_path
            else f"Starting from {contact}, find the vendor's inquiry form or contact option."
        )
        steps = [
            f"1. {found_how}",
            "2. If an inquiry form exists, fill it with the message below, using the signed-in "
            "account's email address; otherwise send the message from the signed-in Gmail account.",
            "3. Submit or send exactly the subject and message below — do not rewrite them.",
        ]
    lines = [
        f"Goal: request a quote from {candidate.name} ({candidate.category}).",
        f"Start at: {start}",
        "Steps:",
        *steps,
        "Message:",
        f"Subject: {draft.subject}",
        draft.message,
        "Constraints:",
        "- Do not accept terms, sign anything, or pay anything.",
        "- If a required form field has no value provided here, stop and report the blocker.",
        "Report: the channel used (form or email), the recipient address or form URL, verbatim "
        "confirmation the message was sent, and any prices or replies you saw.",
    ]
    return "\n".join(lines)


def _render_follow_up_brief(candidate: VendorCandidate, original_subject: str, nudge: OutreachDraft) -> str:
    return "\n".join(
        [
            f"Goal: check for a reply from {candidate.name}, and nudge only if there is none.",
            "Start at: https://mail.google.com",
            "Steps:",
            f"1. In the signed-in Gmail, search for the subject: {original_subject}",
            "2. If the vendor replied, extract the complete reply verbatim — especially prices, "
            "availability, and terms — and report it. Send nothing.",
            "3. Only if there is no reply, send the message below as a reply in the same thread.",
            "Message:",
            nudge.message,
            "Constraints:",
            "- If the original inquiry went through a website form and no email thread exists, "
            "report that instead — never re-submit the form.",
            "- Do not accept terms, sign anything, or pay anything.",
            "Report: whether a reply existed, its verbatim content if so, or confirmation the "
            "follow-up was sent.",
        ]
    )


def _render_reply_brief(candidate: VendorCandidate, subject: str, message: str) -> str:
    contact = candidate.contact_path or candidate.url
    return "\n".join(
        [
            f"Goal: send a negotiation reply to {candidate.name}.",
            "Start at: https://mail.google.com",
            "Steps:",
            f"1. In the signed-in Gmail, search for the subject: {subject}",
            "2. Open the vendor's thread and send the message below as a reply in the same thread.",
            f"3. If no thread exists, send it as a new email via the vendor's contact path: {contact}.",
            "Message:",
            message,
            "Constraints:",
            "- Propose only — do not accept a counter-offer, sign anything, or pay anything.",
            "- Send exactly the message above; do not rewrite it.",
            "Report: confirmation the reply was sent, and the vendor's response if one arrived "
            "while you were in the thread.",
        ]
    )
