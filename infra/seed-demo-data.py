"""Seed the database with the demo event for development.

Transcribes the web app's mock (apps/web/lib/api.ts) verbatim — same slugs, strings,
and list order — so the dashboard renders identically once the getters fetch from the
API instead of the in-memory mock. Re-runnable: it clears the event first, and the
ON DELETE CASCADE foreign keys drop every child row with it.

Run with the agent service's interpreter, e.g.
    services/agent/.venv/bin/python infra/seed-demo-data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# The agent service isn't an installed package; put its root on the path so its
# database modules import exactly as they do when the service runs. In the agent
# container this script sits inside the service root itself, so fall back to that.
_HERE = Path(__file__).resolve()
_REPO_AGENT = _HERE.parents[1] / "services" / "agent"
AGENT_ROOT = _REPO_AGENT if _REPO_AGENT.exists() else _HERE.parent
sys.path.insert(0, str(AGENT_ROOT))

from sqlalchemy import delete  # noqa: E402

from database import models as orm  # noqa: E402
from database.connection import new_session  # noqa: E402

EVENT_ID = "novaflow-summit-2026"


def _seed(session) -> None:
    # Clearing the event cascades to every child row, so re-seeding is idempotent.
    session.execute(delete(orm.Event))

    session.add(
        orm.Event(
            id=EVENT_ID,
            kind="Company summit",
            name="NovaFlow Summit 2026",
            short_name="NovaFlow Summit",
            status_label="On track",
            date="Aug 6, 2026",
            location="Pier 27, SF",
            headcount="320 guests",
            days_to_go="26 days",
            percent_complete=68,
            total_usd=85_000,
            paid_usd=22_100,
            pending_usd=36_300,
            vendors_confirmed=7,
            vendors_total=11,
            vendors_in_progress=4,
            auto_approve_limit="$500",
            savings_footnote="Applying all three keeps you $2,810 under budget with a healthy contingency for day-of surprises.",
        )
    )
    # Persist the aggregate root first: with FK columns but no relationships, the
    # unit of work won't order parent-before-child on its own within one flush.
    session.flush()

    approvals = [
        ("approval-tote-bags", "Purchase", "Purchasing agent", "amber", "Over limit",
         "350 × custom branded tote bags",
         "Exceeds your $500 auto-approve limit. 12-day production plus expedited shipping still clears the Aug 4 setup deadline. Next-cheapest supplier was $3,410.",
         "$2,940", "4imprint", "thread-4imprint"),
        ("approval-dj-deposit", "Booking", "Entertainment agent", "green", "Deposit",
         "DJ — Marina Sound, 4-hour set",
         "Requires a 50% deposit to hold Aug 6. 4.9★ across 120 reviews, brings own PA. Backup on standby: Foghorn DJs at $2,800.",
         "$3,200", "Marina Sound", "thread-marina"),
        ("approval-catering-contract", "Contract", "Catering agent", "green", "Binding contract",
         "Catering agreement — passed apps + plated dinner",
         "Covers 320 guests including 40 vegan and 22 gluten-free. Free cancellation up to 14 days out. Sensitive action: this is a binding contract.",
         "$18,400", "Bi-Rite Catering", "thread-birite"),
    ]
    for i, (id_, kind, agent, tone, tag, title, desc, amount, vendor, thread) in enumerate(approvals):
        session.add(orm.Approval(
            id=id_, event_id=EVENT_ID, kind=kind, agent=agent, agent_tone=tone, tag=tag,
            title=title, description=desc, amount=amount, vendor=vendor, thread_id=thread,
            resolved=False, ordinal=i,
        ))

    agents = [
        ("Venue", "green", "Booked — Pier 27, Aug 6"),
        ("Catering", "blue", "Comparing 3 revised quotes"),
        ("Entertainment", "amber", "Needs your approval — DJ"),
        ("Merchandise", "blue", "Uploading artwork to 4imprint"),
        ("Marketing", "blue", "Drafting the Luma listing"),
        ("Scheduling", "blue", "Syncing 6 calendar holds"),
        ("Staffing", "green", "12 crew confirmed"),
        ("Budget", "gray", "Tracking $58.4k committed"),
    ]
    for i, (name, tone, status) in enumerate(agents):
        session.add(orm.AgentStatusRow(event_id=EVENT_ID, name=name, tone=tone, status=status, ordinal=i))

    activity = [
        ("activity-luma-draft", "Marketing", "blue", "35s ago", "Published a draft Luma listing and generated hero copy for review."),
        ("activity-artwork-upload", "Merchandise", "blue", "2m ago", "Uploaded logo.svg to 4imprint and selected 350 units in navy."),
        ("activity-revised-quote", "Catering", "blue", "6m ago", "Requested a revised quote from Bi-Rite after adding 40 vegan covers."),
        ("activity-walkthrough", "Venue", "green", "14m ago", "Confirmed the final walkthrough — Aug 4 at 10:00 AM with Pier 27."),
        ("activity-deposit-reminder", "Scheduling", "blue", "20m ago", "Added “DJ deposit due” to your calendar for Jul 29."),
        ("activity-tote-flag", "Budget", "amber", "25m ago", "Flagged the tote purchase — it exceeds your auto-approve limit."),
    ]
    for i, (id_, agent, tone, ago, desc) in enumerate(activity):
        session.add(orm.ActivityItem(
            id=id_, event_id=EVENT_ID, agent=agent, tone=tone, time_ago=ago,
            description=desc, pool=False, ordinal=i,
        ))

    activity_pool = [
        ("pool-totes", "Purchasing", "blue", "Compared 3 tote suppliers; 4imprint is cheapest at $8.40 per unit."),
        ("pool-gluten-free", "Catering", "blue", "Bi-Rite replied — they can accommodate all 22 gluten-free guests."),
        ("pool-servers", "Staffing", "green", "Confirmed 12 servers with OnCall Events for the Aug 6 shift."),
        ("pool-crosspost", "Distribution", "blue", "Cross-posted the event to Partiful and Eventbrite."),
        ("pool-coi", "Venue", "green", "Filed the signed Pier 27 certificate of insurance to records."),
        ("pool-dj-hold", "Entertainment", "amber", "Marina Sound is holding Aug 6, pending your deposit approval."),
        ("pool-arrangements", "Decorations", "blue", "Sourced 8 arrangement options from Bloom & Co within budget."),
        ("pool-calendar-sync", "Scheduling", "blue", "Synced 6 vendor calendar holds and resolved a load-in conflict."),
    ]
    for i, (id_, agent, tone, desc) in enumerate(activity_pool):
        session.add(orm.ActivityItem(
            id=id_, event_id=EVENT_ID, agent=agent, tone=tone, time_ago="just now",
            description=desc, pool=True, ordinal=i,
        ))

    vendors = [
        ("vendor-pier27", "P27", "Pier 27", "Venue", "Confirmed", 3, "2h ago", "$24,000"),
        ("vendor-birite", "BR", "Bi-Rite Catering", "Catering", "Awaiting you", 3, "12m ago", "$18,400"),
        ("vendor-stagecraft", "SC", "StageCraft SF", "A/V + staging", "Confirmed", 2, "1d ago", "$9,600"),
        ("vendor-rentals", "SR", "Standard Party Rentals", "Rentals", "Confirmed", 4, "3h ago", "$6,100"),
        ("vendor-oncall", "OC", "OnCall Events", "Staffing · 12 crew", "Confirmed", 2, "5h ago", "$5,200"),
        ("vendor-lumen", "LS", "Lumen Studio", "Photography", "Confirmed", 2, "1d ago", "$3,400"),
        ("vendor-marina", "MS", "Marina Sound", "Entertainment · DJ", "Awaiting you", 3, "6m ago", "$3,200"),
        ("vendor-4imprint", "4i", "4imprint", "Merchandise", "Negotiating", 3, "just now", "$2,940"),
        ("vendor-bloom", "B&", "Bloom & Co", "Decorations", "Sourcing", 8, "20m ago", "~$4,000"),
        ("vendor-ggsigns", "GG", "Golden Gate Signs", "Signage", "Negotiating", 2, "4h ago", "~$1,800"),
        ("vendor-permits", "CP", "City Permits Office", "Permits", "Confirmed", 1, "2d ago", "$650"),
    ]
    for i, (id_, initials, name, category, status, quotes, last, cost) in enumerate(vendors):
        session.add(orm.Vendor(
            id=id_, event_id=EVENT_ID, initials=initials, name=name, category=category,
            status=status, quotes=quotes, last_activity=last, cost=cost, ordinal=i,
        ))

    phases = [
        ("Discovery", 100, "Done"),
        ("Sourcing", 100, "Done"),
        ("Booking", 75, "3 of 4"),
        ("Production", 40, "In progress"),
        ("Day-of", 0, "Aug 6"),
        ("Wrap-up", 0, "Aug 7"),
    ]
    for i, (name, percent, note) in enumerate(phases):
        session.add(orm.PlanPhase(event_id=EVENT_ID, name=name, percent=percent, note=note, ordinal=i))

    groups = [
        ("Venue & space", "Venue", "blue", [
            ("task-book-venue", "Book Pier 27", True),
            ("task-venue-contract", "Sign venue contract", True),
            ("task-walkthrough", "Schedule final walkthrough", True),
        ]),
        ("Food & beverage", "Catering", "green", [
            ("task-catering-quotes", "Collect 3 catering quotes", True),
            ("task-menu", "Finalize menu + dietary needs", False),
            ("task-catering-contract", "Sign catering contract", False),
        ]),
        ("Experience", "Entertainment", "amber", [
            ("task-book-dj", "Book DJ / entertainment", False),
            ("task-av", "Confirm A/V + staging", True),
            ("task-run-of-show", "Plan run-of-show", False),
        ]),
        ("Brand & decor", "Merch", "gray", [
            ("task-merch-artwork", "Approve merch artwork", False),
            ("task-arrangements", "Source arrangements", False),
            ("task-signage", "Order signage", False),
        ]),
        ("People & logistics", "Staffing", "blue", [
            ("task-crew", "Hire event crew (12)", True),
            ("task-shifts", "Confirm staff shifts", True),
            ("task-permits", "File city permits", True),
        ]),
    ]
    for i, (name, owner, tone, tasks) in enumerate(groups):
        group = orm.PlanTaskGroup(event_id=EVENT_ID, name=name, owner=owner, tone=tone, ordinal=i)
        session.add(group)
        session.flush()  # assign group.id before attaching its tasks
        for j, (tid, label, done) in enumerate(tasks):
            session.add(orm.PlanTask(id=tid, group_id=group.id, label=label, done=done, ordinal=j))

    risks = [
        ("Medium", "DJ not yet locked", "Aug 6 is a popular Saturday-adjacent date. Deposit approval is pending; Foghorn DJs held as backup at $2,800."),
        ("Medium", "Merch production is tight", "12-day lead vs. an Aug 4 need. Expedited shipping approved keeps it on schedule with ~1 day of slack."),
        ("Low", "Outdoor cocktail area", "20% chance of rain in the forecast window. Tent rental pre-quoted at $600 and can be added within 48h."),
    ]
    for i, (level, title, mitigation) in enumerate(risks):
        session.add(orm.RiskItem(event_id=EVENT_ID, level=level, title=title, mitigation=mitigation, ordinal=i))

    milestones = [
        ("Requirements captured", "Jul 2", True),
        ("Plan approved", "Jul 4", True),
        ("Venue booked", "Jul 8", True),
        ("Catering signed", "pending", False),
        ("Final headcount", "Aug 1", False),
        ("All vendors confirmed", "Aug 2", False),
    ]
    for i, (title, when, done) in enumerate(milestones):
        session.add(orm.Milestone(event_id=EVENT_ID, title=title, when=when, done=done, ordinal=i))

    categories = [
        ("Venue", 24_000, 12_000, None),
        ("Catering", 18_400, 0, None),
        ("A/V + staging", 9_600, 2_400, None),
        ("Rentals", 6_100, 6_100, None),
        ("Staffing", 5_200, 0, None),
        ("Decorations", 4_000, 0, True),
        ("Photography", 3_400, 950, None),
        ("Entertainment", 3_200, 0, None),
        ("Merchandise", 2_940, 0, None),
        ("Signage", 1_800, 0, True),
        ("Permits", 650, 650, None),
    ]
    for i, (name, committed, paid, estimate) in enumerate(categories):
        session.add(orm.BudgetCategory(
            event_id=EVENT_ID, name=name, committed_usd=committed, paid_usd=paid,
            estimate=estimate, ordinal=i,
        ))

    savings = [
        ("Bundle rentals with venue", "−$490", "Pier 27 gives 8% off tables and linens when booked with the space."),
        ("Sign catering by Jul 30", "−$920", "Bi-Rite waives the 8% service fee for an early signature."),
        ("Switch to Foghorn DJs", "−$400", "Similar 4.8★ reviews at $2,800. Only if you'd rather not stretch the entertainment line."),
    ]
    for i, (title, amount, note) in enumerate(savings):
        session.add(orm.SavingSuggestion(event_id=EVENT_ID, title=title, amount=amount, note=note, ordinal=i))

    calendar = [
        ("2026-07-29", "DJ deposit due", "warn"),
        ("2026-08-01", "Headcount due", "warn"),
        ("2026-08-02", "Merch artwork", "info"),
        ("2026-08-03", "Tasting call · 2 PM", "info"),
        ("2026-08-04", "Walkthrough · 10 AM", "info"),
        ("2026-08-04", "Venue payment", "warn"),
        ("2026-08-05", "Rehearsal · 4 PM", "info"),
        ("2026-08-06", "★ Event day", "accent"),
        ("2026-08-07", "Vendor payouts", "info"),
        ("2026-08-07", "Teardown", "muted"),
    ]
    for i, (date, title, kind) in enumerate(calendar):
        session.add(orm.CalendarEvent(event_id=EVENT_ID, date=date, title=title, kind=kind, ordinal=i))

    agenda = [
        ("agenda-dj-deposit", "Jul", "29", "DJ deposit due", "Marina Sound · $1,600", "urgent"),
        ("agenda-headcount", "Aug", "01", "Final headcount to caterer", "Bi-Rite", None),
        ("agenda-tasting", "Aug", "03", "Catering tasting call", "2:00 PM · video", None),
        ("agenda-walkthrough", "Aug", "04", "Venue walkthrough + payment", "10 AM · $12,000 due", None),
        ("agenda-rehearsal", "Aug", "05", "Rehearsal & setup", "4:00 PM at Pier 27", None),
        ("agenda-event-day", "Aug", "06", "Event day", "Load-in 8 AM · doors 7 PM", "event"),
    ]
    for i, (id_, month, day, title, meta, emphasis) in enumerate(agenda):
        session.add(orm.DeadlineItem(
            id=id_, event_id=EVENT_ID, list_kind="agenda", month=month, day=day,
            title=title, meta=meta, emphasis=emphasis, ordinal=i,
        ))

    deadlines = [
        ("deadline-dj-deposit", "Jul", "29", "DJ deposit due", "Marina Sound · $1,600", "urgent"),
        ("deadline-headcount", "Aug", "01", "Final headcount to caterer", "Bi-Rite · lock guest count", None),
        ("deadline-artwork", "Aug", "02", "Merch artwork approval", "4imprint · print-ready deadline", None),
        ("deadline-venue-payment", "Aug", "04", "Venue final payment", "Pier 27 · $12,000", None),
        ("deadline-event-day", "Aug", "06", "Event day", "Load-in 8:00 AM", "event"),
    ]
    for i, (id_, month, day, title, meta, emphasis) in enumerate(deadlines):
        session.add(orm.DeadlineItem(
            id=id_, event_id=EVENT_ID, list_kind="key", month=month, day=day,
            title=title, meta=meta, emphasis=emphasis, ordinal=i,
        ))

    decisions = [
        ("decision-pier27", "Pier 27 venue deposit", "$12,000", "2d ago", True),
        ("decision-stagecraft", "StageCraft A/V — 50% deposit", "$4,800", "3d ago", True),
        ("decision-rentals", "Standard Party Rentals", "$6,100", "3d ago", True),
        ("decision-foghorn", "Foghorn DJs (declined for Marina)", "$2,800", "4d ago", False),
        ("decision-lumen", "Lumen Studio deposit", "$1,700", "5d ago", True),
    ]
    for i, (id_, title, amount, when, approved) in enumerate(decisions):
        session.add(orm.DecisionRecord(
            id=id_, event_id=EVENT_ID, title=title, amount=amount, when=when, approved=approved, ordinal=i,
        ))

    rules = [
        ("rule-purchases", "Purchases under the limit", "Auto"),
        ("rule-contracts", "Vendor contracts", "Ask first"),
        ("rule-deposits", "Deposits & payments", "Ask first"),
        ("rule-emails", "Sending emails", "Auto"),
        ("rule-private-data", "Sharing private data", "Ask first"),
    ]
    for i, (id_, label, value) in enumerate(rules):
        session.add(orm.SpendingRule(id=id_, event_id=EVENT_ID, label=label, value=value, ordinal=i))

    post_event = [
        ("post-pay-vendors", "$", "Pay outstanding vendors", "Release final balances to 11 vendors per contract terms.", "Scheduled"),
        ("post-thank-you", "✉", "Send thank-you emails", "Personalized notes to vendors and speakers.", "Draft ready"),
        ("post-survey", "★", "Run attendee feedback survey", "3-question NPS survey to 320 guests.", "Draft ready"),
        ("post-reconcile", "∑", "Reconcile the budget", "Match receipts, flag variances, close the ledger.", "Scheduled"),
        ("post-refunds", "↻", "Request eligible refunds", "Unused rentals and the weather-tent deposit.", "Scheduled"),
        ("post-photos", "▣", "Collect photos & video", "Gather deliverables from Lumen Studio into a shared album.", "Scheduled"),
    ]
    for i, (id_, glyph, title, desc, state) in enumerate(post_event):
        session.add(orm.PostEventTask(
            id=id_, event_id=EVENT_ID, glyph=glyph, title=title, description=desc, state=state, ordinal=i,
        ))

    conversations = [
        {
            "id": "thread-pier27", "name": "Dana Whitfield", "subtitle": "Venue manager · Pier 27",
            "channel": "Email", "avatar_initials": "DW", "time_label": "Jul 9",
            "preview": "Confirmed for Aug 4 at 10:00 AM — meet at the north gate and we'll walk the floor…",
            "unread": True, "archived": False,
            "quick_replies": ["Confirm 10:00 AM works", "Ask about dock access"],
            "messages": [
                ("pier27-1", "You", True, "Tue, Jul 7", "9:42 AM", "Hi Dana,\n\nAhead of the summit on Aug 6 we'd like a final walkthrough of the floor plan, load-in route, and AV setup. Would the morning of Aug 4 work on your end?"),
                ("pier27-2", "Dana", None, "Thu, Jul 9", "8:05 AM", "Morning! Aug 4 works.\n\nConfirmed for Aug 4 at 10:00 AM — meet at the north gate and we'll walk the floor, the loading dock, and the green room. Plan for about an hour."),
                ("pier27-3", "Dana", None, "Thu, Jul 9", "8:11 AM", "One more thing — if your caterer needs early dock access on event day, send me their vehicle plates by Jul 30 so security can pre-clear them."),
            ],
        },
        {
            "id": "thread-birite", "name": "Marco Reyes", "subtitle": "Catering coordinator · Bi-Rite Catering",
            "channel": "Vendor portal", "avatar_initials": "MR", "time_label": "Jul 8",
            "preview": "Revised quote attached: $18,400 for 320 covers including the 40 vegan and 22 gluten-free…",
            "unread": True, "archived": False,
            "quick_replies": ["Looks good — send the contract", "Ask about service staff"],
            "messages": [
                ("birite-1", "Marco", None, "Wed, Jul 8", "4:27 PM", "Hi Amresh,\n\nRevised quote attached: $18,400 for 320 covers including the 40 vegan and 22 gluten-free meals your team added — passed apps on arrival, plated dinner at 7:00 PM.\n\nSetup starts at 3:30 PM and cleanup wraps by 11:00 PM. Free cancellation up to 14 days out. Let me know if you want to lock this in and I'll send the agreement."),
            ],
        },
        {
            "id": "thread-marina", "name": "Marina Sound", "subtitle": "Booking · Marina Sound",
            "channel": "Email", "avatar_initials": "MS", "time_label": "Jul 8",
            "preview": "To hold Aug 6 we'd need the 50% deposit ($1,600) by Jul 29 — invoice attached…",
            "unread": True, "archived": False,
            "quick_replies": ["Request a W-9 first"],
            "messages": [
                ("marina-1", "Marina Sound", None, "Wed, Jul 8", "1:58 PM", "Hey! Great chatting about the NovaFlow Summit after-party set.\n\nTo hold Aug 6 we'd need the 50% deposit ($1,600) by Jul 29 — invoice attached. The 4-hour set includes our PA and lighting rig; we just need a 20A circuit within 50 ft of the stage.\n\nSend over any must-play (or do-not-play) lists whenever."),
            ],
        },
        {
            "id": "thread-4imprint", "name": "4imprint Support", "subtitle": "Order #88214 · 4imprint",
            "channel": "Vendor portal", "avatar_initials": "4I", "time_label": "Jul 7",
            "preview": "Artwork proof approved. Production starts today — 350 navy totes, 12-day run plus expedited…",
            "unread": False, "archived": False,
            "quick_replies": ["Ask for tracking number"],
            "messages": [
                ("4imprint-1", "4imprint Support", None, "Tue, Jul 7", "10:15 AM", "Artwork proof approved. Production starts today — 350 navy totes, 12-day run plus expedited shipping, arriving on or before Aug 4.\n\nYou'll get tracking as soon as the order leaves the warehouse."),
            ],
        },
        {
            "id": "thread-eventstaff", "name": "Priya Shah", "subtitle": "Staffing lead · EventStaff Pro",
            "channel": "SMS", "avatar_initials": "PS", "time_label": "Jul 6",
            "preview": "All 12 crew confirmed for Aug 6: 4 registration, 4 setup/cleanup, 2 bartenders, 2 AV…",
            "unread": True, "archived": False,
            "quick_replies": ["Share the shift schedule"],
            "messages": [
                ("eventstaff-1", "Priya", None, "Mon, Jul 6", "5:44 PM", "All 12 crew confirmed for Aug 6: 4 registration, 4 setup/cleanup, 2 bartenders, 2 AV.\n\nFirst shift starts 1:00 PM for setup. I'll send individual contact cards the week of the event."),
            ],
        },
        {
            "id": "thread-luma", "name": "Luma", "subtitle": "Listing review · Luma",
            "channel": "Luma", "avatar_initials": "LU", "time_label": "Jul 5",
            "preview": "Your draft event page is ready for review — NovaFlow Summit 2026, Aug 6, Pier 27…",
            "unread": False, "archived": False,
            "quick_replies": [],
            "messages": [
                ("luma-1", "Luma", None, "Sun, Jul 5", "11:03 AM", "Your draft event page is ready for review — NovaFlow Summit 2026, Aug 6, Pier 27.\n\nPublish when ready, or share the preview link with your team for comments."),
            ],
        },
        {
            "id": "thread-foghorn", "name": "Foghorn DJs", "subtitle": "Backup quote · Foghorn DJs",
            "channel": "Email", "avatar_initials": "FD", "time_label": "Jun 30",
            "preview": "No problem — we'll release the courtesy hold on Aug 6. If anything changes, the $2,800 quote…",
            "unread": False, "archived": True,
            "quick_replies": [],
            "messages": [
                ("foghorn-1", "Foghorn DJs", None, "Tue, Jun 30", "2:20 PM", "No problem — we'll release the courtesy hold on Aug 6. If anything changes, the $2,800 quote stands through Jul 25."),
            ],
        },
        {
            "id": "thread-gallery308", "name": "Gallery 308", "subtitle": "Venue inquiry · Fort Mason Center",
            "channel": "Email", "avatar_initials": "G3", "time_label": "Jun 21",
            "preview": "Thanks for considering Gallery 308. We've added you to the waitlist for Aug 6 in case…",
            "unread": False, "archived": True,
            "quick_replies": [],
            "messages": [
                ("gallery308-1", "Gallery 308", None, "Sun, Jun 21", "9:30 AM", "Thanks for considering Gallery 308. We've added you to the waitlist for Aug 6 in case your primary venue falls through — no obligation either way."),
            ],
        },
    ]
    for i, convo in enumerate(conversations):
        session.add(orm.Conversation(
            id=convo["id"], event_id=EVENT_ID, name=convo["name"], subtitle=convo["subtitle"],
            channel=convo["channel"], avatar_initials=convo["avatar_initials"], time_label=convo["time_label"],
            preview=convo["preview"], unread=convo["unread"], archived=convo["archived"],
            quick_replies=convo["quick_replies"], ordinal=i,
        ))
        session.flush()  # the conversation must exist before its messages insert
        for j, (mid, author, from_me, day, time, body) in enumerate(convo["messages"]):
            session.add(orm.InboxMessage(
                id=mid, conversation_id=convo["id"], author=author, from_me=from_me,
                day=day, time=time, body=body, ordinal=j,
            ))


def main() -> None:
    session = new_session()
    try:
        _seed(session)
        session.commit()
        print(f"Seeded demo event {EVENT_ID!r}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
