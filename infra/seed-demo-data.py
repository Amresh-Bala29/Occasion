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
ROOFTOP_ID = "rooftop-party"
HACKATHON_ID = "hackathon"


def _seed(session) -> None:
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


def _seed_rooftop(session) -> None:
    # Demo fixture A: an intake prompt mentioning "cake" swaps the dashboard to this event.
    session.add(
        orm.Event(
            id=ROOFTOP_ID,
            kind="Birthday party",
            name="Skyline 30th Birthday",
            short_name="Skyline 30th",
            status_label="On track",
            date="Aug 15, 2026",
            location="Rooftop 25, SoMa",
            headcount="75 guests",
            days_to_go="34 days",
            percent_complete=62,
            total_usd=18_000,
            paid_usd=5_300,
            pending_usd=6_900,
            vendors_confirmed=4,
            vendors_total=9,
            vendors_in_progress=5,
            auto_approve_limit="$400",
            savings_footnote="Applying all three keeps you $6,400 under budget with a healthy contingency for day-of surprises.",
        )
    )
    session.flush()

    approvals = [
        ("approval-rt-cake", "Purchase", "Catering agent", "amber", "Over limit",
         "Custom 3-tier celebration cake — Sugarbloom Bakery",
         "Exceeds your $400 auto-approve limit. Lemon-elderflower with gold leaf, serves 80, delivered chilled at 5 PM on Aug 15. Next-cheapest quote was $520.",
         "$680", "Sugarbloom Bakery", "thread-sugarbloom"),
        ("approval-rt-dj-deposit", "Booking", "Entertainment agent", "green", "Deposit",
         "DJ — Skyline Sounds, 4-hour set",
         "Requires a 50% deposit to hold Aug 15. 4.9★ across 90 reviews, brings own PA and lights. Backup on standby: Nightshift DJs at $1,400.",
         "$1,600", "Skyline Sounds", "thread-skyline-dj"),
        ("approval-rt-bar-contract", "Contract", "Catering agent", "green", "Binding contract",
         "Open-bar service — 75 guests, 5 hours",
         "Beer, wine, and two signature cocktails with two bartenders. Free cancellation up to 10 days out. Sensitive action: this is a binding contract.",
         "$3,200", "Copper & Rye Bar Co.", "thread-copper-rye"),
    ]
    for i, (id_, kind, agent, tone, tag, title, desc, amount, vendor, thread) in enumerate(approvals):
        session.add(orm.Approval(
            id=id_, event_id=ROOFTOP_ID, kind=kind, agent=agent, agent_tone=tone, tag=tag,
            title=title, description=desc, amount=amount, vendor=vendor, thread_id=thread,
            resolved=False, ordinal=i,
        ))

    agents = [
        ("Venue", "green", "Booked — Rooftop 25, Aug 15"),
        ("Catering", "amber", "Needs your approval — cake"),
        ("Entertainment", "amber", "Needs your approval — DJ"),
        ("Decorations", "blue", "Sourcing string lights + florals"),
        ("Photography", "green", "Booked — Aperture Studio"),
        ("Scheduling", "blue", "Syncing 5 calendar holds"),
        ("Staffing", "green", "6 servers confirmed"),
        ("Budget", "gray", "Tracking $12.2k committed"),
    ]
    for i, (name, tone, status) in enumerate(agents):
        session.add(orm.AgentStatusRow(event_id=ROOFTOP_ID, name=name, tone=tone, status=status, ordinal=i))

    activity = [
        ("activity-rt-cake-flag", "Catering", "amber", "40s ago", "Flagged the custom cake — it exceeds your auto-approve limit."),
        ("activity-rt-lights", "Decorations", "blue", "3m ago", "Sourced warm string-light runs and 6 low-floral centerpieces within budget."),
        ("activity-rt-photographer", "Photography", "green", "11m ago", "Confirmed Aperture Studio for a 4-hour golden-hour shoot."),
        ("activity-rt-weather", "Venue", "amber", "18m ago", "Checked the Aug 15 forecast and pre-quoted a clear-tent backup at $450."),
        ("activity-rt-bar", "Catering", "blue", "24m ago", "Requested an open-bar contract from Copper & Rye for 75 guests."),
        ("activity-rt-dj-hold", "Entertainment", "amber", "31m ago", "Skyline Sounds is holding Aug 15 pending your deposit approval."),
    ]
    for i, (id_, agent, tone, ago, desc) in enumerate(activity):
        session.add(orm.ActivityItem(
            id=id_, event_id=ROOFTOP_ID, agent=agent, tone=tone, time_ago=ago,
            description=desc, pool=False, ordinal=i,
        ))

    activity_pool = [
        ("pool-rt-cake-tasting", "Catering", "blue", "Booked a cake tasting with Sugarbloom for Aug 5 at 2 PM."),
        ("pool-rt-servers", "Staffing", "green", "Confirmed 6 servers with CityHost Staffing for the Aug 15 shift."),
        ("pool-rt-permit", "Venue", "green", "Filed the rooftop amplified-sound permit — approved through 11 PM."),
        ("pool-rt-rentals", "Decorations", "blue", "Compared lounge-furniture rentals; Loft & Co is cheapest for the terrace."),
        ("pool-rt-florals", "Decorations", "blue", "Sourced 6 low-floral centerpieces from Petal & Stem within budget."),
        ("pool-rt-invites", "Marketing", "blue", "Sent the Partiful invite to 90 contacts; 61 RSVPed yes."),
        ("pool-rt-cocktails", "Catering", "blue", "Finalized two signature cocktails with Copper & Rye."),
        ("pool-rt-playlist", "Entertainment", "amber", "Shared the must-play list with Skyline Sounds for approval."),
    ]
    for i, (id_, agent, tone, desc) in enumerate(activity_pool):
        session.add(orm.ActivityItem(
            id=id_, event_id=ROOFTOP_ID, agent=agent, tone=tone, time_ago="just now",
            description=desc, pool=True, ordinal=i,
        ))

    vendors = [
        ("vendor-rt-rooftop25", "R2", "Rooftop 25", "Venue", "Confirmed", 2, "3h ago", "$5,500"),
        ("vendor-rt-graze", "GG", "Graze & Gather", "Catering", "Confirmed", 3, "2h ago", "$3,900"),
        ("vendor-rt-copper", "CR", "Copper & Rye Bar Co.", "Bar service", "Awaiting you", 2, "24m ago", "$3,200"),
        ("vendor-rt-skyline", "SS", "Skyline Sounds", "Entertainment · DJ", "Awaiting you", 3, "31m ago", "$1,600"),
        ("vendor-rt-aperture", "AS", "Aperture Studio", "Photography", "Confirmed", 2, "11m ago", "$1,500"),
        ("vendor-rt-loft", "LC", "Loft & Co Rentals", "Rentals · Lounge", "Sourcing", 4, "1h ago", "~$1,400"),
        ("vendor-rt-petal", "PS", "Petal & Stem", "Decorations · Florals", "Negotiating", 3, "1h ago", "~$1,200"),
        ("vendor-rt-cityhost", "CH", "CityHost Staffing", "Staffing · 6 crew", "Confirmed", 1, "5h ago", "$1,100"),
        ("vendor-rt-sugarbloom", "SB", "Sugarbloom Bakery", "Catering · Cake", "Awaiting you", 2, "40s ago", "$680"),
    ]
    for i, (id_, initials, name, category, status, quotes, last, cost) in enumerate(vendors):
        session.add(orm.Vendor(
            id=id_, event_id=ROOFTOP_ID, initials=initials, name=name, category=category,
            status=status, quotes=quotes, last_activity=last, cost=cost, ordinal=i,
        ))

    phases = [
        ("Discovery", 100, "Done"),
        ("Sourcing", 100, "Done"),
        ("Booking", 60, "3 of 5"),
        ("Production", 35, "In progress"),
        ("Day-of", 0, "Aug 15"),
        ("Wrap-up", 0, "Aug 16"),
    ]
    for i, (name, percent, note) in enumerate(phases):
        session.add(orm.PlanPhase(event_id=ROOFTOP_ID, name=name, percent=percent, note=note, ordinal=i))

    groups = [
        ("Venue & space", "Venue", "blue", [
            ("task-rt-book-venue", "Book Rooftop 25", True),
            ("task-rt-permit", "File amplified-sound permit", True),
            ("task-rt-tent", "Hold weather-tent backup", False),
        ]),
        ("Food & cake", "Catering", "amber", [
            ("task-rt-catering", "Confirm passed apps + stations", True),
            ("task-rt-cake", "Approve custom cake", False),
            ("task-rt-bar", "Sign open-bar contract", False),
        ]),
        ("Experience", "Entertainment", "amber", [
            ("task-rt-dj", "Book DJ", False),
            ("task-rt-playlist", "Finalize playlist", False),
            ("task-rt-photographer", "Book photographer", True),
        ]),
        ("Decor & ambiance", "Decor", "gray", [
            ("task-rt-lights", "Hang string lights", False),
            ("task-rt-florals", "Source florals", False),
            ("task-rt-lounge", "Order lounge furniture", False),
        ]),
        ("People & logistics", "Staffing", "blue", [
            ("task-rt-servers", "Hire servers (6)", True),
            ("task-rt-shifts", "Confirm staff shifts", True),
            ("task-rt-timeline", "Set day-of timeline", False),
        ]),
    ]
    for i, (name, owner, tone, tasks) in enumerate(groups):
        group = orm.PlanTaskGroup(event_id=ROOFTOP_ID, name=name, owner=owner, tone=tone, ordinal=i)
        session.add(group)
        session.flush()  # assign group.id before attaching its tasks
        for j, (tid, label, done) in enumerate(tasks):
            session.add(orm.PlanTask(id=tid, group_id=group.id, label=label, done=done, ordinal=j))

    risks = [
        ("Medium", "Rooftop weather exposure", "20% chance of evening showers on Aug 15. A clear-tent backup is pre-quoted at $450 and can be confirmed within 48h."),
        ("Medium", "DJ not yet locked", "Aug 15 is a popular summer Saturday. Deposit approval is pending; Nightshift DJs held as backup at $1,400."),
        ("Low", "Cake in summer heat", "Buttercream softens above 80°F. Sugarbloom delivers chilled at 5 PM and stages the cake indoors until it's cut."),
    ]
    for i, (level, title, mitigation) in enumerate(risks):
        session.add(orm.RiskItem(event_id=ROOFTOP_ID, level=level, title=title, mitigation=mitigation, ordinal=i))

    milestones = [
        ("Requirements captured", "Jul 5", True),
        ("Plan approved", "Jul 8", True),
        ("Venue booked", "Jul 12", True),
        ("Cake approved", "pending", False),
        ("Final headcount", "Aug 8", False),
        ("All vendors confirmed", "Aug 10", False),
    ]
    for i, (title, when, done) in enumerate(milestones):
        session.add(orm.Milestone(event_id=ROOFTOP_ID, title=title, when=when, done=done, ordinal=i))

    categories = [
        ("Venue", 5_200, 2_750, None),
        ("Catering", 3_300, 1_800, None),
        ("Bar service", 2_200, 0, None),
        ("Entertainment", 1_600, 0, None),
        ("Photography", 1_500, 750, None),
        ("Decorations", 1_200, 0, True),
        ("Rentals", 1_100, 0, True),
        ("Staffing", 1_100, 0, None),
        ("Cake", 680, 0, None),
    ]
    for i, (name, committed, paid, estimate) in enumerate(categories):
        session.add(orm.BudgetCategory(
            event_id=ROOFTOP_ID, name=name, committed_usd=committed, paid_usd=paid,
            estimate=estimate, ordinal=i,
        ))

    savings = [
        ("Bundle rentals with the venue", "−$180", "Rooftop 25 gives 10% off lounge furniture when it's booked with the space."),
        ("Book cake + catering together", "−$220", "Graze & Gather waives the delivery fee if Sugarbloom's cake ships with their order."),
        ("Switch to Nightshift DJs", "−$200", "Similar 4.8★ reviews at $1,400. Only if you'd rather not stretch the entertainment line."),
    ]
    for i, (title, amount, note) in enumerate(savings):
        session.add(orm.SavingSuggestion(event_id=ROOFTOP_ID, title=title, amount=amount, note=note, ordinal=i))

    calendar = [
        ("2026-08-05", "Cake tasting · 2 PM", "info"),
        ("2026-08-08", "Headcount due", "warn"),
        ("2026-08-10", "DJ deposit due", "warn"),
        ("2026-08-12", "Florals + lights load-in", "info"),
        ("2026-08-13", "Venue walkthrough · 11 AM", "info"),
        ("2026-08-14", "Rehearsal / setup · 5 PM", "info"),
        ("2026-08-14", "Venue balance due", "warn"),
        ("2026-08-15", "★ Party day", "accent"),
        ("2026-08-16", "Vendor payouts", "info"),
        ("2026-08-16", "Teardown", "muted"),
    ]
    for i, (date, title, kind) in enumerate(calendar):
        session.add(orm.CalendarEvent(event_id=ROOFTOP_ID, date=date, title=title, kind=kind, ordinal=i))

    agenda = [
        ("agenda-rt-cake-tasting", "Aug", "05", "Cake tasting", "Sugarbloom · 2:00 PM", None),
        ("agenda-rt-headcount", "Aug", "08", "Final headcount", "Lock the guest count", None),
        ("agenda-rt-dj-deposit", "Aug", "10", "DJ deposit due", "Skyline Sounds · $800", "urgent"),
        ("agenda-rt-walkthrough", "Aug", "13", "Venue walkthrough", "11 AM · Rooftop 25", None),
        ("agenda-rt-rehearsal", "Aug", "14", "Rehearsal & setup", "5:00 PM on the terrace", None),
        ("agenda-rt-party-day", "Aug", "15", "Party day", "Load-in 3 PM · doors 7 PM", "event"),
    ]
    for i, (id_, month, day, title, meta, emphasis) in enumerate(agenda):
        session.add(orm.DeadlineItem(
            id=id_, event_id=ROOFTOP_ID, list_kind="agenda", month=month, day=day,
            title=title, meta=meta, emphasis=emphasis, ordinal=i,
        ))

    deadlines = [
        ("deadline-rt-cake", "Aug", "05", "Custom cake approval", "Sugarbloom · confirm design", None),
        ("deadline-rt-headcount", "Aug", "08", "Final headcount to caterer", "Graze & Gather · lock count", None),
        ("deadline-rt-dj-deposit", "Aug", "10", "DJ deposit due", "Skyline Sounds · $800", "urgent"),
        ("deadline-rt-venue-balance", "Aug", "14", "Venue final payment", "Rooftop 25 · $2,750", None),
        ("deadline-rt-party-day", "Aug", "15", "Party day", "Load-in 3:00 PM", "event"),
    ]
    for i, (id_, month, day, title, meta, emphasis) in enumerate(deadlines):
        session.add(orm.DeadlineItem(
            id=id_, event_id=ROOFTOP_ID, list_kind="key", month=month, day=day,
            title=title, meta=meta, emphasis=emphasis, ordinal=i,
        ))

    decisions = [
        ("decision-rt-rooftop25", "Rooftop 25 deposit", "$2,750", "2d ago", True),
        ("decision-rt-graze", "Graze & Gather — 50% deposit", "$1,950", "3d ago", True),
        ("decision-rt-aperture", "Aperture Studio deposit", "$750", "3d ago", True),
        ("decision-rt-nightshift", "Nightshift DJs (declined for Skyline)", "$1,400", "4d ago", False),
        ("decision-rt-permit", "Rooftop sound permit", "$120", "5d ago", True),
    ]
    for i, (id_, title, amount, when, approved) in enumerate(decisions):
        session.add(orm.DecisionRecord(
            id=id_, event_id=ROOFTOP_ID, title=title, amount=amount, when=when, approved=approved, ordinal=i,
        ))

    rules = [
        ("rule-rt-purchases", "Purchases under the limit", "Auto"),
        ("rule-rt-contracts", "Vendor contracts", "Ask first"),
        ("rule-rt-deposits", "Deposits & payments", "Ask first"),
        ("rule-rt-emails", "Sending emails", "Auto"),
        ("rule-rt-private-data", "Sharing private data", "Ask first"),
    ]
    for i, (id_, label, value) in enumerate(rules):
        session.add(orm.SpendingRule(id=id_, event_id=ROOFTOP_ID, label=label, value=value, ordinal=i))

    post_event = [
        ("post-rt-pay-vendors", "$", "Pay outstanding vendors", "Release final balances to 9 vendors per contract terms.", "Scheduled"),
        ("post-rt-thank-you", "✉", "Send thank-you notes", "Personalized notes to guests who traveled in.", "Draft ready"),
        ("post-rt-photos", "▣", "Collect photos", "Gather the gallery from Aperture Studio into a shared album.", "Scheduled"),
        ("post-rt-reconcile", "∑", "Reconcile the budget", "Match receipts, flag variances, close the ledger.", "Scheduled"),
        ("post-rt-refunds", "↻", "Request eligible refunds", "Unused tent-backup hold and any rental over-count.", "Scheduled"),
        ("post-rt-survey", "★", "Send a quick guest survey", "3-question note to 75 guests.", "Draft ready"),
    ]
    for i, (id_, glyph, title, desc, state) in enumerate(post_event):
        session.add(orm.PostEventTask(
            id=id_, event_id=ROOFTOP_ID, glyph=glyph, title=title, description=desc, state=state, ordinal=i,
        ))

    conversations = [
        {
            "id": "thread-sugarbloom", "name": "Nadia Okafor", "subtitle": "Pastry chef · Sugarbloom Bakery",
            "channel": "Email", "avatar_initials": "NO", "time_label": "Jul 10",
            "preview": "Design locked: a 3-tier lemon-elderflower cake with gold leaf, serving 80 — delivered chilled at 5 PM…",
            "unread": True, "archived": False,
            "quick_replies": ["Approve the design", "Ask about a gluten-free tier"],
            "messages": [
                ("sugarbloom-1", "You", True, "Wed, Jul 8", "10:12 AM", "Hi Nadia,\n\nFor the rooftop 30th on Aug 15 we'd love a show-stopping cake for about 75 guests — something summery. Open to your ideas on flavor and finish."),
                ("sugarbloom-2", "Nadia", None, "Fri, Jul 10", "9:03 AM", "Love it! Design locked: a 3-tier lemon-elderflower cake with gold leaf, serving 80 — delivered chilled at 5 PM so it holds in the heat.\n\nQuote is $680 with delivery. Want me to send the proof to approve?"),
            ],
        },
        {
            "id": "thread-rooftop25", "name": "Theo Marsh", "subtitle": "Events manager · Rooftop 25",
            "channel": "Email", "avatar_initials": "TM", "time_label": "Jul 9",
            "preview": "You're confirmed for Aug 15. Load-in from 3 PM via the freight elevator; amplified sound is fine until 11 PM…",
            "unread": True, "archived": False,
            "quick_replies": ["Confirm 3 PM load-in", "Ask about the tent backup"],
            "messages": [
                ("rooftop25-1", "Theo", None, "Thu, Jul 9", "2:20 PM", "You're confirmed for Aug 15! Load-in from 3 PM via the freight elevator; amplified sound is fine until 11 PM with the permit on file.\n\nIf the forecast turns, we can add the clear-tent canopy for $450 up to 48 hours out."),
            ],
        },
        {
            "id": "thread-skyline-dj", "name": "Skyline Sounds", "subtitle": "Booking · Skyline Sounds",
            "channel": "Email", "avatar_initials": "SS", "time_label": "Jul 8",
            "preview": "To hold Aug 15 we'd need the 50% deposit ($800) by Aug 10 — invoice attached…",
            "unread": True, "archived": False,
            "quick_replies": ["Send the must-play list"],
            "messages": [
                ("skyline-dj-1", "Skyline Sounds", None, "Wed, Jul 8", "1:40 PM", "Great chatting about the rooftop set! To hold Aug 15 we'd need the 50% deposit ($800) by Aug 10 — invoice attached.\n\nThe 4-hour set includes our PA and lights; we just need a 20A circuit near the DJ table. Send any must-play or do-not-play lists whenever."),
            ],
        },
        {
            "id": "thread-copper-rye", "name": "Marisol Vega", "subtitle": "Bar lead · Copper & Rye Bar Co.",
            "channel": "Vendor portal", "avatar_initials": "MV", "time_label": "Jul 7",
            "preview": "Open-bar package for 75: beer, wine, two signature cocktails, two bartenders — $3,200…",
            "unread": False, "archived": False,
            "quick_replies": ["Looks good — send the contract"],
            "messages": [
                ("copper-rye-1", "Marisol", None, "Tue, Jul 7", "4:10 PM", "Hi! Open-bar package for 75: beer, wine, two signature cocktails, and two bartenders for 5 hours — $3,200.\n\nWe handle setup and cleanup, and offer free cancellation up to 10 days out. Say the word and I'll send the agreement."),
            ],
        },
        {
            "id": "thread-petal", "name": "Petal & Stem", "subtitle": "Florals · Petal & Stem",
            "channel": "Email", "avatar_initials": "PS", "time_label": "Jul 6",
            "preview": "Six low centerpieces in warm tones with trailing greenery — $1,200 installed on Aug 14…",
            "unread": False, "archived": False,
            "quick_replies": ["Approve the palette"],
            "messages": [
                ("petal-1", "Petal & Stem", None, "Mon, Jul 6", "11:25 AM", "Proposal attached: six low centerpieces in warm tones with trailing greenery, plus a small install along the bar — $1,200 installed on Aug 14.\n\nHappy to swap in dahlias if you'd like more of a late-summer look."),
            ],
        },
        {
            "id": "thread-nightshift", "name": "Nightshift DJs", "subtitle": "Backup quote · Nightshift DJs",
            "channel": "Email", "avatar_initials": "ND", "time_label": "Jun 29",
            "preview": "No problem — we'll hold Aug 15 as a courtesy. The $1,400 quote stands through Jul 20…",
            "unread": False, "archived": True,
            "quick_replies": [],
            "messages": [
                ("nightshift-1", "Nightshift DJs", None, "Mon, Jun 29", "3:15 PM", "No problem — we'll hold Aug 15 as a courtesy backup. The $1,400 quote stands through Jul 20 if anything changes."),
            ],
        },
    ]
    for i, convo in enumerate(conversations):
        session.add(orm.Conversation(
            id=convo["id"], event_id=ROOFTOP_ID, name=convo["name"], subtitle=convo["subtitle"],
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


def _seed_hackathon(session) -> None:
    # Demo fixture B: an intake prompt mentioning "pizza" swaps the dashboard to this event.
    session.add(
        orm.Event(
            id=HACKATHON_ID,
            kind="Hackathon",
            name="NovaHacks 2026",
            short_name="NovaHacks",
            status_label="On track",
            date="Aug 22, 2026",
            location="Innovation Hall, SoMa",
            headcount="200 hackers",
            days_to_go="41 days",
            percent_complete=55,
            total_usd=42_000,
            paid_usd=10_400,
            pending_usd=16_100,
            vendors_confirmed=5,
            vendors_total=11,
            vendors_in_progress=6,
            auto_approve_limit="$750",
            savings_footnote="Applying all three keeps you $3,200 under budget with a reserve for overflow pizza and prizes.",
        )
    )
    session.flush()

    approvals = [
        ("approval-hack-pizza", "Contract", "Catering agent", "green", "Binding contract",
         "Pizza catering — 120 pies across the weekend",
         "Fri dinner, Sat lunch/dinner, Sun lunch for 200 hackers, including 30 vegan and 18 gluten-free pies. Free cancellation up to 7 days out. Sensitive action: this is a binding contract.",
         "$4,800", "Tony's Pizza Kitchen", "thread-tonys"),
        ("approval-hack-prizes", "Purchase", "Purchasing agent", "amber", "Over limit",
         "Prize pool — cash + hardware",
         "Exceeds your $750 auto-approve limit. $10,000 cash across three tracks plus six flagship laptops for the category winners.",
         "$12,000", "Prize pool", "thread-prizes"),
        ("approval-hack-av", "Booking", "Scheduling agent", "green", "Deposit",
         "AV + networking gear rental — 3-day",
         "Requires a 40% deposit to reserve. 200-device Wi-Fi, 12 access points, stage AV, and 400A power distro. Backup vendor: MetroAV at $6,900.",
         "$6,200", "GigaStage AV", "thread-gigastage"),
        ("approval-hack-swag", "Purchase", "Merchandise agent", "amber", "Over limit",
         "Event swag — 220 shirts + stickers + lanyards",
         "Exceeds your $750 auto-approve limit. 8-day production plus standard shipping clears the Aug 20 stuffing deadline. Next-cheapest supplier was $3,050.",
         "$2,640", "PrintHaus", "thread-printhaus"),
    ]
    for i, (id_, kind, agent, tone, tag, title, desc, amount, vendor, thread) in enumerate(approvals):
        session.add(orm.Approval(
            id=id_, event_id=HACKATHON_ID, kind=kind, agent=agent, agent_tone=tone, tag=tag,
            title=title, description=desc, amount=amount, vendor=vendor, thread_id=thread,
            resolved=False, ordinal=i,
        ))

    agents = [
        ("Venue", "green", "Booked — Innovation Hall, Aug 22"),
        ("Catering", "green", "Pizza contract ready for sign-off"),
        ("Tech/AV", "amber", "Needs your approval — networking gear"),
        ("Purchasing", "amber", "Needs your approval — prize pool"),
        ("Merchandise", "blue", "Uploading artwork to PrintHaus"),
        ("Scheduling", "blue", "Syncing 8 calendar holds"),
        ("Staffing", "green", "Security + volunteers confirmed"),
        ("Budget", "gray", "Tracking $26.5k committed"),
    ]
    for i, (name, tone, status) in enumerate(agents):
        session.add(orm.AgentStatusRow(event_id=HACKATHON_ID, name=name, tone=tone, status=status, ordinal=i))

    activity = [
        ("activity-hack-pizza", "Catering", "green", "45s ago", "Locked Tony's Pizza — 120 pies across the weekend, vegan and gluten-free included."),
        ("activity-hack-prizes", "Purchasing", "amber", "4m ago", "Flagged the $12,000 prize pool — it exceeds your auto-approve limit."),
        ("activity-hack-wifi", "Tech/AV", "amber", "9m ago", "Sized the network for 200 devices — quoted 12 access points from GigaStage."),
        ("activity-hack-swag", "Merchandise", "blue", "15m ago", "Uploaded the NovaHacks logo to PrintHaus and selected 220 shirts."),
        ("activity-hack-judges", "Scheduling", "blue", "22m ago", "Confirmed 6 of 8 judges for the Sunday demo session."),
        ("activity-hack-security", "Staffing", "green", "28m ago", "Confirmed overnight security for the Fri–Sun lock-in."),
    ]
    for i, (id_, agent, tone, ago, desc) in enumerate(activity):
        session.add(orm.ActivityItem(
            id=id_, event_id=HACKATHON_ID, agent=agent, tone=tone, time_ago=ago,
            description=desc, pool=False, ordinal=i,
        ))

    activity_pool = [
        ("pool-hack-power", "Tech/AV", "blue", "Mapped 400A power distribution across 40 team tables."),
        ("pool-hack-coffee", "Catering", "blue", "Added a 24-hour coffee and energy-drink station from JavaCart."),
        ("pool-hack-volunteers", "Staffing", "green", "Confirmed 15 student volunteers for check-in and floats."),
        ("pool-hack-sponsors", "Marketing", "blue", "Cross-posted the CFP to Luma and Devpost; 240 signups so far."),
        ("pool-hack-cleaning", "Venue", "blue", "Booked an overnight cleaning crew for the Sat→Sun turnover."),
        ("pool-hack-lanyards", "Merchandise", "blue", "Sourced 220 lanyards and badge holders within budget."),
        ("pool-hack-firstaid", "Staffing", "amber", "Arranged an on-call medic for the overnight hours."),
        ("pool-hack-tables", "Scheduling", "blue", "Reserved 40 tables and 200 chairs from Metro Rentals."),
    ]
    for i, (id_, agent, tone, desc) in enumerate(activity_pool):
        session.add(orm.ActivityItem(
            id=id_, event_id=HACKATHON_ID, agent=agent, tone=tone, time_ago="just now",
            description=desc, pool=True, ordinal=i,
        ))

    vendors = [
        ("vendor-hack-hall", "IH", "Innovation Hall", "Venue", "Confirmed", 2, "3h ago", "$9,000"),
        ("vendor-hack-tonys", "TP", "Tony's Pizza Kitchen", "Catering · Pizza", "Awaiting you", 3, "45s ago", "$4,800"),
        ("vendor-hack-gigastage", "GS", "GigaStage AV", "A/V + networking", "Awaiting you", 3, "9m ago", "$6,200"),
        ("vendor-hack-prizes", "PP", "Prize Pool", "Prizes", "Awaiting you", 1, "4m ago", "$12,000"),
        ("vendor-hack-metro", "MR", "Metro Rentals", "Rentals · Tables", "Confirmed", 4, "1h ago", "$2,200"),
        ("vendor-hack-shield", "SH", "Shield Security", "Security · Overnight", "Confirmed", 2, "28m ago", "$3,100"),
        ("vendor-hack-javacart", "JC", "JavaCart", "Catering · Coffee", "Confirmed", 2, "2h ago", "$1,900"),
        ("vendor-hack-sparkle", "SC", "Sparkle Cleaning Co.", "Cleaning", "Confirmed", 1, "50m ago", "$1,200"),
        ("vendor-hack-printhaus", "PH", "PrintHaus", "Merchandise · Swag", "Negotiating", 3, "15m ago", "$2,640"),
        ("vendor-hack-lumen", "LV", "Lumen Video", "Photo + video", "Sourcing", 5, "35m ago", "~$2,500"),
        ("vendor-hack-medic", "OM", "OnCall Medics", "Medical", "Negotiating", 2, "20m ago", "~$900"),
    ]
    for i, (id_, initials, name, category, status, quotes, last, cost) in enumerate(vendors):
        session.add(orm.Vendor(
            id=id_, event_id=HACKATHON_ID, initials=initials, name=name, category=category,
            status=status, quotes=quotes, last_activity=last, cost=cost, ordinal=i,
        ))

    phases = [
        ("Discovery", 100, "Done"),
        ("Sourcing", 100, "Done"),
        ("Booking", 55, "5 of 9"),
        ("Production", 30, "In progress"),
        ("Day-of", 0, "Aug 22"),
        ("Wrap-up", 0, "Aug 24"),
    ]
    for i, (name, percent, note) in enumerate(phases):
        session.add(orm.PlanPhase(event_id=HACKATHON_ID, name=name, percent=percent, note=note, ordinal=i))

    groups = [
        ("Venue & space", "Venue", "green", [
            ("task-hack-book-venue", "Book Innovation Hall", True),
            ("task-hack-power", "Confirm power + Wi-Fi plan", False),
            ("task-hack-cleaning", "Book overnight cleaning", True),
        ]),
        ("Food & pizza", "Catering", "blue", [
            ("task-hack-pizza", "Sign pizza contract", False),
            ("task-hack-coffee", "Confirm coffee station", True),
            ("task-hack-dietary", "Confirm vegan + GF counts", True),
        ]),
        ("Tech & networking", "Tech/AV", "amber", [
            ("task-hack-wifi", "Approve networking gear", False),
            ("task-hack-av", "Confirm stage AV", False),
            ("task-hack-tables", "Reserve tables + power", True),
        ]),
        ("Prizes & swag", "Merch", "amber", [
            ("task-hack-prizes", "Approve prize pool", False),
            ("task-hack-swag", "Approve swag artwork", False),
            ("task-hack-lanyards", "Order lanyards + badges", True),
        ]),
        ("People & safety", "Staffing", "green", [
            ("task-hack-security", "Hire overnight security", True),
            ("task-hack-volunteers", "Confirm 15 volunteers", True),
            ("task-hack-medic", "Arrange on-call medic", False),
        ]),
    ]
    for i, (name, owner, tone, tasks) in enumerate(groups):
        group = orm.PlanTaskGroup(event_id=HACKATHON_ID, name=name, owner=owner, tone=tone, ordinal=i)
        session.add(group)
        session.flush()  # assign group.id before attaching its tasks
        for j, (tid, label, done) in enumerate(tasks):
            session.add(orm.PlanTask(id=tid, group_id=group.id, label=label, done=done, ordinal=j))

    risks = [
        ("High", "Wi-Fi bandwidth for 200 devices", "A hackathon lives on the network. GigaStage quoted 12 access points and a dedicated 1 Gbps line; approval is pending so the install can be tested Aug 21."),
        ("Medium", "Overnight power distribution", "40 team tables drawing laptops and monitors need 400A distro. Metro Rentals is confirmed; an electrician runs a load check at setup."),
        ("Medium", "Overnight security & liability", "A Fri–Sun lock-in needs continuous security and a medic. Shield Security is confirmed; OnCall Medics is finalizing the overnight rate."),
    ]
    for i, (level, title, mitigation) in enumerate(risks):
        session.add(orm.RiskItem(event_id=HACKATHON_ID, level=level, title=title, mitigation=mitigation, ordinal=i))

    milestones = [
        ("Requirements captured", "Jul 3", True),
        ("Plan approved", "Jul 6", True),
        ("Venue booked", "Jul 10", True),
        ("Pizza contract signed", "pending", False),
        ("Final headcount", "Aug 15", False),
        ("All vendors confirmed", "Aug 18", False),
    ]
    for i, (title, when, done) in enumerate(milestones):
        session.add(orm.Milestone(event_id=HACKATHON_ID, title=title, when=when, done=done, ordinal=i))

    categories = [
        ("Prizes", 12_000, 0, None),
        ("Venue", 9_000, 4_500, None),
        ("A/V + networking", 6_200, 0, None),
        ("Catering · Pizza", 4_800, 0, None),
        ("Security", 3_100, 1_550, None),
        ("Merchandise", 2_640, 0, None),
        ("Photo + video", 2_500, 0, True),
        ("Rentals", 2_200, 2_200, None),
        ("Coffee + snacks", 1_900, 950, None),
        ("Cleaning", 1_200, 1_200, None),
        ("Medical", 900, 0, True),
    ]
    for i, (name, committed, paid, estimate) in enumerate(categories):
        session.add(orm.BudgetCategory(
            event_id=HACKATHON_ID, name=name, committed_usd=committed, paid_usd=paid,
            estimate=estimate, ordinal=i,
        ))

    savings = [
        ("Bundle A/V with the venue", "−$620", "Innovation Hall gives 10% off networking gear booked through their preferred vendor."),
        ("Order swag by Aug 12", "−$310", "PrintHaus waives the rush fee for a standard 8-day run."),
        ("Trim the prize hardware tier", "−$900", "Swap two of the six flagship laptops for the prior model — same category, $900 back."),
    ]
    for i, (title, amount, note) in enumerate(savings):
        session.add(orm.SavingSuggestion(event_id=HACKATHON_ID, title=title, amount=amount, note=note, ordinal=i))

    calendar = [
        ("2026-08-12", "Swag order deadline", "warn"),
        ("2026-08-14", "Networking install test", "info"),
        ("2026-08-15", "Final headcount", "warn"),
        ("2026-08-17", "Judge briefing · 3 PM", "info"),
        ("2026-08-19", "AV deposit due", "warn"),
        ("2026-08-20", "Swag stuffing · 6 PM", "info"),
        ("2026-08-21", "Load-in + power check", "info"),
        ("2026-08-22", "★ Hackathon kickoff", "accent"),
        ("2026-08-24", "Demos + awards", "accent"),
        ("2026-08-24", "Teardown", "muted"),
    ]
    for i, (date, title, kind) in enumerate(calendar):
        session.add(orm.CalendarEvent(event_id=HACKATHON_ID, date=date, title=title, kind=kind, ordinal=i))

    agenda = [
        ("agenda-hack-swag", "Aug", "12", "Swag order deadline", "PrintHaus · print-ready", None),
        ("agenda-hack-install", "Aug", "14", "Networking install test", "GigaStage · on-site", None),
        ("agenda-hack-headcount", "Aug", "15", "Final headcount", "Lock the participant count", None),
        ("agenda-hack-av-deposit", "Aug", "19", "AV deposit due", "GigaStage · $2,480", "urgent"),
        ("agenda-hack-loadin", "Aug", "21", "Load-in + power check", "9 AM · Innovation Hall", None),
        ("agenda-hack-kickoff", "Aug", "22", "Hackathon kickoff", "Doors 5 PM · hacking 7 PM", "event"),
    ]
    for i, (id_, month, day, title, meta, emphasis) in enumerate(agenda):
        session.add(orm.DeadlineItem(
            id=id_, event_id=HACKATHON_ID, list_kind="agenda", month=month, day=day,
            title=title, meta=meta, emphasis=emphasis, ordinal=i,
        ))

    deadlines = [
        ("deadline-hack-swag", "Aug", "12", "Swag artwork deadline", "PrintHaus · print-ready", None),
        ("deadline-hack-headcount", "Aug", "15", "Final headcount to caterer", "Tony's Pizza · lock count", None),
        ("deadline-hack-av-deposit", "Aug", "19", "AV deposit due", "GigaStage · $2,480", "urgent"),
        ("deadline-hack-loadin", "Aug", "21", "Venue load-in", "9:00 AM power check", None),
        ("deadline-hack-kickoff", "Aug", "22", "Hackathon kickoff", "Doors 5:00 PM", "event"),
    ]
    for i, (id_, month, day, title, meta, emphasis) in enumerate(deadlines):
        session.add(orm.DeadlineItem(
            id=id_, event_id=HACKATHON_ID, list_kind="key", month=month, day=day,
            title=title, meta=meta, emphasis=emphasis, ordinal=i,
        ))

    decisions = [
        ("decision-hack-hall", "Innovation Hall deposit", "$4,500", "3d ago", True),
        ("decision-hack-rentals", "Metro Rentals — tables + chairs", "$2,200", "3d ago", True),
        ("decision-hack-security", "Shield Security — 50% deposit", "$1,550", "4d ago", True),
        ("decision-hack-metroav", "MetroAV (declined for GigaStage)", "$6,900", "4d ago", False),
        ("decision-hack-cleaning", "Sparkle Cleaning overnight crew", "$1,200", "5d ago", True),
    ]
    for i, (id_, title, amount, when, approved) in enumerate(decisions):
        session.add(orm.DecisionRecord(
            id=id_, event_id=HACKATHON_ID, title=title, amount=amount, when=when, approved=approved, ordinal=i,
        ))

    rules = [
        ("rule-hack-purchases", "Purchases under the limit", "Auto"),
        ("rule-hack-contracts", "Vendor contracts", "Ask first"),
        ("rule-hack-deposits", "Deposits & payments", "Ask first"),
        ("rule-hack-emails", "Sending emails", "Auto"),
        ("rule-hack-private-data", "Sharing private data", "Ask first"),
    ]
    for i, (id_, label, value) in enumerate(rules):
        session.add(orm.SpendingRule(id=id_, event_id=HACKATHON_ID, label=label, value=value, ordinal=i))

    post_event = [
        ("post-hack-pay-vendors", "$", "Pay outstanding vendors", "Release final balances to 11 vendors per contract terms.", "Scheduled"),
        ("post-hack-prizes", "★", "Disburse prize payouts", "Send cash prizes to three winning teams and ship the hardware.", "Scheduled"),
        ("post-hack-thank-you", "✉", "Thank sponsors + judges", "Personalized notes to 8 judges and 4 sponsors.", "Draft ready"),
        ("post-hack-survey", "▣", "Run the participant survey", "5-question feedback survey to 200 hackers.", "Draft ready"),
        ("post-hack-reconcile", "∑", "Reconcile the budget", "Match receipts, flag variances, close the ledger.", "Scheduled"),
        ("post-hack-recap", "↻", "Publish the recap + projects", "Gather Devpost submissions and photos into a recap post.", "Scheduled"),
    ]
    for i, (id_, glyph, title, desc, state) in enumerate(post_event):
        session.add(orm.PostEventTask(
            id=id_, event_id=HACKATHON_ID, glyph=glyph, title=title, description=desc, state=state, ordinal=i,
        ))

    conversations = [
        {
            "id": "thread-tonys", "name": "Tony Marchetti", "subtitle": "Owner · Tony's Pizza Kitchen",
            "channel": "Email", "avatar_initials": "TM", "time_label": "Jul 11",
            "preview": "120 pies across the weekend — Fri dinner, Sat lunch/dinner, Sun lunch, with 30 vegan and 18 GF…",
            "unread": True, "archived": False,
            "quick_replies": ["Send the contract", "Add 10 more vegan pies"],
            "messages": [
                ("tonys-1", "You", True, "Wed, Jul 9", "9:30 AM", "Hi Tony,\n\nWe're running NovaHacks Aug 22–24 for ~200 hackers and we'll need a lot of pizza across the weekend. Can you handle staggered drops and dietary options?"),
                ("tonys-2", "Tony", None, "Sat, Jul 11", "12:14 PM", "Absolutely — this is our specialty. Plan: 120 pies across the weekend — Fri dinner, Sat lunch and dinner, Sun lunch, with 30 vegan and 18 gluten-free pies.\n\nQuote is $4,800 with delivery and warmers. Free cancellation up to 7 days out. Want the contract?"),
            ],
        },
        {
            "id": "thread-gigastage", "name": "Renée Park", "subtitle": "Solutions lead · GigaStage AV",
            "channel": "Vendor portal", "avatar_initials": "RP", "time_label": "Jul 10",
            "preview": "For 200 devices we'd run 12 access points and a dedicated 1 Gbps line, plus stage AV — $6,200…",
            "unread": True, "archived": False,
            "quick_replies": ["Approve the deposit", "Ask about a backup line"],
            "messages": [
                ("gigastage-1", "Renée", None, "Fri, Jul 10", "2:05 PM", "Hi! For 200 devices we'd run 12 access points and a dedicated 1 Gbps line, plus stage AV for the kickoff and demos — $6,200.\n\nWe'd install and load-test on Aug 21. A 40% deposit reserves the gear and the crew."),
            ],
        },
        {
            "id": "thread-prizes", "name": "Jordan Blake", "subtitle": "Sponsorship · NovaFlow",
            "channel": "Email", "avatar_initials": "JB", "time_label": "Jul 9",
            "preview": "Confirmed the $12,000 prize pool: $10k cash across three tracks plus six flagship laptops…",
            "unread": False, "archived": False,
            "quick_replies": ["Approve the pool"],
            "messages": [
                ("prizes-1", "Jordan", None, "Wed, Jul 9", "4:40 PM", "Confirmed the $12,000 prize pool: $10k cash across three tracks plus six flagship laptops for the category winners.\n\nFinance needs your approval before we wire the cash prizes — the hardware ships from our vendor."),
            ],
        },
        {
            "id": "thread-printhaus", "name": "PrintHaus Support", "subtitle": "Order #40912 · PrintHaus",
            "channel": "Vendor portal", "avatar_initials": "PH", "time_label": "Jul 8",
            "preview": "Artwork received — 220 shirts, stickers, and lanyards, 8-day run arriving on or before Aug 20…",
            "unread": False, "archived": False,
            "quick_replies": ["Approve the proof"],
            "messages": [
                ("printhaus-1", "PrintHaus Support", None, "Tue, Jul 8", "10:22 AM", "Artwork received — 220 shirts, stickers, and lanyards, 8-day run arriving on or before Aug 20.\n\nApprove the proof and we'll start production; you'll get tracking when it ships."),
            ],
        },
        {
            "id": "thread-shield", "name": "Priya Nair", "subtitle": "Ops · Shield Security",
            "channel": "SMS", "avatar_initials": "PN", "time_label": "Jul 7",
            "preview": "Overnight coverage confirmed for Fri–Sun: two guards on rotation plus badge checks at the door…",
            "unread": True, "archived": False,
            "quick_replies": ["Share the floor plan"],
            "messages": [
                ("shield-1", "Priya", None, "Mon, Jul 7", "6:10 PM", "Overnight coverage confirmed for Fri–Sun: two guards on rotation plus badge checks at the door.\n\nSend the floor plan and we'll set patrol points for the lock-in."),
            ],
        },
        {
            "id": "thread-metroav", "name": "MetroAV", "subtitle": "Backup quote · MetroAV",
            "channel": "Email", "avatar_initials": "MA", "time_label": "Jun 28",
            "preview": "Holding your dates as a courtesy. The $6,900 quote for AV + networking stands through Jul 18…",
            "unread": False, "archived": True,
            "quick_replies": [],
            "messages": [
                ("metroav-1", "MetroAV", None, "Sun, Jun 28", "1:05 PM", "Holding your dates as a courtesy backup. The $6,900 quote for AV + networking stands through Jul 18 if anything changes with your primary vendor."),
            ],
        },
    ]
    for i, convo in enumerate(conversations):
        session.add(orm.Conversation(
            id=convo["id"], event_id=HACKATHON_ID, name=convo["name"], subtitle=convo["subtitle"],
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
        # Clear all events once; the ON DELETE CASCADE FKs drop every child row, so
        # re-seeding is idempotent and also sweeps throwaway events left by demo runs.
        session.execute(delete(orm.Event))
        _seed(session)
        _seed_rooftop(session)
        _seed_hackathon(session)
        session.commit()
        print(f"Seeded demo events: {EVENT_ID!r}, {ROOFTOP_ID!r}, {HACKATHON_ID!r}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
