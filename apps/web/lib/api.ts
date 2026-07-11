// API layer for the Occasion web app. Components call these functions instead
// of fetch()ing directly so backend wiring stays in one place.
import type {
  ActivityItem,
  BudgetDetail,
  CalendarEventItem,
  Conversation,
  DashboardData,
  DeadlineItem,
  DecisionRecord,
  EventPlan,
  PostEventTask,
  SessionResult,
  SpendingRule,
  Vendor,
} from "@/types";

const AGENT_URL = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000";

/**
 * Run one natural-language browser task through the agent service.
 * The request blocks until the session settles, which can take a few minutes.
 */
export async function runComputerUseTask(task: string): Promise<SessionResult> {
  let response: Response;
  try {
    response = await fetch(`${AGENT_URL}/api/computer-use/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task }),
    });
  } catch {
    throw new Error(`Could not reach the agent service at ${AGENT_URL}. Is it running?`);
  }
  if (!response.ok) {
    throw new Error(`Agent service returned ${response.status}: ${await readErrorDetail(response)}`);
  }
  return (await response.json()) as SessionResult;
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
  } catch {
    return response.statusText || "unknown error";
  }
}

/** Dashboard data is mocked until the events API lands; swap this for a fetch then. */
export function getDashboardData(): DashboardData {
  return MOCK_DASHBOARD;
}

/** Inbox threads are mocked until the messages API lands; swap this for a fetch then. */
export function getInboxConversations(): Conversation[] {
  return MOCK_INBOX;
}

/** Every vendor on the event; the vendors panel filters this list by status. */
export function getVendors(): Vendor[] {
  return MOCK_VENDORS;
}

/** Phases, task checklist, risks, and milestones for the plan board. */
export function getEventPlan(): EventPlan {
  return MOCK_PLAN;
}

/** Per-category spend and suggested savings for the budget panel. */
export function getBudgetDetail(): BudgetDetail {
  return MOCK_BUDGET_DETAIL;
}

/** Dated items rendered on the calendar month grid. */
export function getCalendarEvents(): CalendarEventItem[] {
  return MOCK_CALENDAR_EVENTS;
}

/** The "Upcoming" rail beside the calendar. */
export function getCalendarAgenda(): DeadlineItem[] {
  return MOCK_AGENDA;
}

/** The short deadline list on the overview page. */
export function getKeyDeadlines(): DeadlineItem[] {
  return MOCK_DEADLINES;
}

/** Already-decided approvals shown under "Recent decisions". */
export function getDecisionHistory(): DecisionRecord[] {
  return MOCK_DECISIONS;
}

/** Which action classes run automatically vs. pause for sign-off. */
export function getSpendingRules(): SpendingRule[] {
  return MOCK_SPENDING_RULES;
}

/** Wrap-up work queued to run automatically after the event. */
export function getPostEventTasks(): PostEventTask[] {
  return MOCK_POST_EVENT_TASKS;
}

/** Rotating pool of simulated agent updates that feed the live activity rail. */
export function getActivityPool(): ActivityItem[] {
  return MOCK_ACTIVITY_POOL;
}

const MOCK_DASHBOARD: DashboardData = {
  event: {
    id: "novaflow-summit-2026",
    kind: "Company summit",
    name: "NovaFlow Summit 2026",
    shortName: "NovaFlow Summit",
    statusLabel: "On track",
    date: "Aug 6, 2026",
    location: "Pier 27, SF",
    headcount: "320 guests",
    daysToGo: "26 days",
    percentComplete: 68,
  },
  budget: {
    totalUsd: 85_000,
    paidUsd: 22_100,
    pendingUsd: 36_300,
  },
  vendors: {
    confirmed: 7,
    total: 11,
    inProgress: 4,
  },
  approvals: [
    {
      id: "approval-tote-bags",
      kind: "Purchase",
      agent: "Purchasing agent",
      agentTone: "amber",
      tag: "Over limit",
      title: "350 × custom branded tote bags",
      description:
        "Exceeds your $500 auto-approve limit. 12-day production plus expedited shipping still clears the Aug 4 setup deadline. Next-cheapest supplier was $3,410.",
      amount: "$2,940",
      vendor: "4imprint",
      threadId: "thread-4imprint",
    },
    {
      id: "approval-dj-deposit",
      kind: "Booking",
      agent: "Entertainment agent",
      agentTone: "green",
      tag: "Deposit",
      title: "DJ — Marina Sound, 4-hour set",
      description:
        "Requires a 50% deposit to hold Aug 6. 4.9★ across 120 reviews, brings own PA. Backup on standby: Foghorn DJs at $2,800.",
      amount: "$3,200",
      vendor: "Marina Sound",
      threadId: "thread-marina",
    },
    {
      id: "approval-catering-contract",
      kind: "Contract",
      agent: "Catering agent",
      agentTone: "green",
      tag: "Binding contract",
      title: "Catering agreement — passed apps + plated dinner",
      description:
        "Covers 320 guests including 40 vegan and 22 gluten-free. Free cancellation up to 14 days out. Sensitive action: this is a binding contract.",
      amount: "$18,400",
      vendor: "Bi-Rite Catering",
      threadId: "thread-birite",
    },
  ],
  agents: [
    { name: "Venue", tone: "green", status: "Booked — Pier 27, Aug 6" },
    { name: "Catering", tone: "blue", status: "Comparing 3 revised quotes" },
    { name: "Entertainment", tone: "amber", status: "Needs your approval — DJ" },
    { name: "Merchandise", tone: "blue", status: "Uploading artwork to 4imprint" },
    { name: "Marketing", tone: "blue", status: "Drafting the Luma listing" },
    { name: "Scheduling", tone: "blue", status: "Syncing 6 calendar holds" },
    { name: "Staffing", tone: "green", status: "12 crew confirmed" },
    { name: "Budget", tone: "gray", status: "Tracking $58.4k committed" },
  ],
  activity: [
    {
      id: "activity-luma-draft",
      agent: "Marketing",
      tone: "blue",
      timeAgo: "35s ago",
      description: "Published a draft Luma listing and generated hero copy for review.",
    },
    {
      id: "activity-artwork-upload",
      agent: "Merchandise",
      tone: "blue",
      timeAgo: "2m ago",
      description: "Uploaded logo.svg to 4imprint and selected 350 units in navy.",
    },
    {
      id: "activity-revised-quote",
      agent: "Catering",
      tone: "blue",
      timeAgo: "6m ago",
      description: "Requested a revised quote from Bi-Rite after adding 40 vegan covers.",
    },
    {
      id: "activity-walkthrough",
      agent: "Venue",
      tone: "green",
      timeAgo: "14m ago",
      description: "Confirmed the final walkthrough — Aug 4 at 10:00 AM with Pier 27.",
    },
    {
      id: "activity-deposit-reminder",
      agent: "Scheduling",
      tone: "blue",
      timeAgo: "20m ago",
      description: "Added “DJ deposit due” to your calendar for Jul 29.",
    },
    {
      id: "activity-tote-flag",
      agent: "Budget",
      tone: "amber",
      timeAgo: "25m ago",
      description: "Flagged the tote purchase — it exceeds your auto-approve limit.",
    },
  ],
  agentsWorking: 8,
  messagesCount: 4,
  autoApproveLimit: "$500",
};

// Unread count here stays in sync with MOCK_DASHBOARD.messagesCount.
const MOCK_INBOX: Conversation[] = [
  {
    id: "thread-pier27",
    name: "Dana Whitfield",
    subtitle: "Venue manager · Pier 27",
    channel: "Email",
    avatarInitials: "DW",
    timeLabel: "Jul 9",
    preview: "Confirmed for Aug 4 at 10:00 AM — meet at the north gate and we'll walk the floor…",
    unread: true,
    archived: false,
    quickReplies: ["Confirm 10:00 AM works", "Ask about dock access"],
    messages: [
      {
        id: "pier27-1",
        author: "You",
        fromMe: true,
        day: "Tue, Jul 7",
        time: "9:42 AM",
        body: "Hi Dana,\n\nAhead of the summit on Aug 6 we'd like a final walkthrough of the floor plan, load-in route, and AV setup. Would the morning of Aug 4 work on your end?",
      },
      {
        id: "pier27-2",
        author: "Dana",
        day: "Thu, Jul 9",
        time: "8:05 AM",
        body: "Morning! Aug 4 works.\n\nConfirmed for Aug 4 at 10:00 AM — meet at the north gate and we'll walk the floor, the loading dock, and the green room. Plan for about an hour.",
      },
      {
        id: "pier27-3",
        author: "Dana",
        day: "Thu, Jul 9",
        time: "8:11 AM",
        body: "One more thing — if your caterer needs early dock access on event day, send me their vehicle plates by Jul 30 so security can pre-clear them.",
      },
    ],
  },
  {
    id: "thread-birite",
    name: "Marco Reyes",
    subtitle: "Catering coordinator · Bi-Rite Catering",
    channel: "Vendor portal",
    avatarInitials: "MR",
    timeLabel: "Jul 8",
    preview: "Revised quote attached: $18,400 for 320 covers including the 40 vegan and 22 gluten-free…",
    unread: true,
    archived: false,
    quickReplies: ["Looks good — send the contract", "Ask about service staff"],
    messages: [
      {
        id: "birite-1",
        author: "Marco",
        day: "Wed, Jul 8",
        time: "4:27 PM",
        body: "Hi Amresh,\n\nRevised quote attached: $18,400 for 320 covers including the 40 vegan and 22 gluten-free meals your team added — passed apps on arrival, plated dinner at 7:00 PM.\n\nSetup starts at 3:30 PM and cleanup wraps by 11:00 PM. Free cancellation up to 14 days out. Let me know if you want to lock this in and I'll send the agreement.",
      },
    ],
  },
  {
    id: "thread-marina",
    name: "Marina Sound",
    subtitle: "Booking · Marina Sound",
    channel: "Email",
    avatarInitials: "MS",
    timeLabel: "Jul 8",
    preview: "To hold Aug 6 we'd need the 50% deposit ($1,600) by Jul 29 — invoice attached…",
    unread: true,
    archived: false,
    quickReplies: ["Request a W-9 first"],
    messages: [
      {
        id: "marina-1",
        author: "Marina Sound",
        day: "Wed, Jul 8",
        time: "1:58 PM",
        body: "Hey! Great chatting about the NovaFlow Summit after-party set.\n\nTo hold Aug 6 we'd need the 50% deposit ($1,600) by Jul 29 — invoice attached. The 4-hour set includes our PA and lighting rig; we just need a 20A circuit within 50 ft of the stage.\n\nSend over any must-play (or do-not-play) lists whenever.",
      },
    ],
  },
  {
    id: "thread-4imprint",
    name: "4imprint Support",
    subtitle: "Order #88214 · 4imprint",
    channel: "Vendor portal",
    avatarInitials: "4I",
    timeLabel: "Jul 7",
    preview: "Artwork proof approved. Production starts today — 350 navy totes, 12-day run plus expedited…",
    unread: false,
    archived: false,
    quickReplies: ["Ask for tracking number"],
    messages: [
      {
        id: "4imprint-1",
        author: "4imprint Support",
        day: "Tue, Jul 7",
        time: "10:15 AM",
        body: "Artwork proof approved. Production starts today — 350 navy totes, 12-day run plus expedited shipping, arriving on or before Aug 4.\n\nYou'll get tracking as soon as the order leaves the warehouse.",
      },
    ],
  },
  {
    id: "thread-eventstaff",
    name: "Priya Shah",
    subtitle: "Staffing lead · EventStaff Pro",
    channel: "SMS",
    avatarInitials: "PS",
    timeLabel: "Jul 6",
    preview: "All 12 crew confirmed for Aug 6: 4 registration, 4 setup/cleanup, 2 bartenders, 2 AV…",
    unread: true,
    archived: false,
    quickReplies: ["Share the shift schedule"],
    messages: [
      {
        id: "eventstaff-1",
        author: "Priya",
        day: "Mon, Jul 6",
        time: "5:44 PM",
        body: "All 12 crew confirmed for Aug 6: 4 registration, 4 setup/cleanup, 2 bartenders, 2 AV.\n\nFirst shift starts 1:00 PM for setup. I'll send individual contact cards the week of the event.",
      },
    ],
  },
  {
    id: "thread-luma",
    name: "Luma",
    subtitle: "Listing review · Luma",
    channel: "Luma",
    avatarInitials: "LU",
    timeLabel: "Jul 5",
    preview: "Your draft event page is ready for review — NovaFlow Summit 2026, Aug 6, Pier 27…",
    unread: false,
    archived: false,
    quickReplies: [],
    messages: [
      {
        id: "luma-1",
        author: "Luma",
        day: "Sun, Jul 5",
        time: "11:03 AM",
        body: "Your draft event page is ready for review — NovaFlow Summit 2026, Aug 6, Pier 27.\n\nPublish when ready, or share the preview link with your team for comments.",
      },
    ],
  },
  {
    id: "thread-foghorn",
    name: "Foghorn DJs",
    subtitle: "Backup quote · Foghorn DJs",
    channel: "Email",
    avatarInitials: "FD",
    timeLabel: "Jun 30",
    preview: "No problem — we'll release the courtesy hold on Aug 6. If anything changes, the $2,800 quote…",
    unread: false,
    archived: true,
    quickReplies: [],
    messages: [
      {
        id: "foghorn-1",
        author: "Foghorn DJs",
        day: "Tue, Jun 30",
        time: "2:20 PM",
        body: "No problem — we'll release the courtesy hold on Aug 6. If anything changes, the $2,800 quote stands through Jul 25.",
      },
    ],
  },
  {
    id: "thread-gallery308",
    name: "Gallery 308",
    subtitle: "Venue inquiry · Fort Mason Center",
    channel: "Email",
    avatarInitials: "G3",
    timeLabel: "Jun 21",
    preview: "Thanks for considering Gallery 308. We've added you to the waitlist for Aug 6 in case…",
    unread: false,
    archived: true,
    quickReplies: [],
    messages: [
      {
        id: "gallery308-1",
        author: "Gallery 308",
        day: "Sun, Jun 21",
        time: "9:30 AM",
        body: "Thanks for considering Gallery 308. We've added you to the waitlist for Aug 6 in case your primary venue falls through — no obligation either way.",
      },
    ],
  },
];

const MOCK_VENDORS: Vendor[] = [
  { id: "vendor-pier27", initials: "P27", name: "Pier 27", category: "Venue", status: "Confirmed", quotes: 3, lastActivity: "2h ago", cost: "$24,000" },
  { id: "vendor-birite", initials: "BR", name: "Bi-Rite Catering", category: "Catering", status: "Awaiting you", quotes: 3, lastActivity: "12m ago", cost: "$18,400" },
  { id: "vendor-stagecraft", initials: "SC", name: "StageCraft SF", category: "A/V + staging", status: "Confirmed", quotes: 2, lastActivity: "1d ago", cost: "$9,600" },
  { id: "vendor-rentals", initials: "SR", name: "Standard Party Rentals", category: "Rentals", status: "Confirmed", quotes: 4, lastActivity: "3h ago", cost: "$6,100" },
  { id: "vendor-oncall", initials: "OC", name: "OnCall Events", category: "Staffing · 12 crew", status: "Confirmed", quotes: 2, lastActivity: "5h ago", cost: "$5,200" },
  { id: "vendor-lumen", initials: "LS", name: "Lumen Studio", category: "Photography", status: "Confirmed", quotes: 2, lastActivity: "1d ago", cost: "$3,400" },
  { id: "vendor-marina", initials: "MS", name: "Marina Sound", category: "Entertainment · DJ", status: "Awaiting you", quotes: 3, lastActivity: "6m ago", cost: "$3,200" },
  { id: "vendor-4imprint", initials: "4i", name: "4imprint", category: "Merchandise", status: "Negotiating", quotes: 3, lastActivity: "just now", cost: "$2,940" },
  { id: "vendor-bloom", initials: "B&", name: "Bloom & Co", category: "Decorations", status: "Sourcing", quotes: 8, lastActivity: "20m ago", cost: "~$4,000" },
  { id: "vendor-ggsigns", initials: "GG", name: "Golden Gate Signs", category: "Signage", status: "Negotiating", quotes: 2, lastActivity: "4h ago", cost: "~$1,800" },
  { id: "vendor-permits", initials: "CP", name: "City Permits Office", category: "Permits", status: "Confirmed", quotes: 1, lastActivity: "2d ago", cost: "$650" },
];

const MOCK_PLAN: EventPlan = {
  phases: [
    { name: "Discovery", percent: 100, note: "Done" },
    { name: "Sourcing", percent: 100, note: "Done" },
    { name: "Booking", percent: 75, note: "3 of 4" },
    { name: "Production", percent: 40, note: "In progress" },
    { name: "Day-of", percent: 0, note: "Aug 6" },
    { name: "Wrap-up", percent: 0, note: "Aug 7" },
  ],
  groups: [
    {
      name: "Venue & space",
      owner: "Venue",
      tone: "blue",
      tasks: [
        { id: "task-book-venue", label: "Book Pier 27", done: true },
        { id: "task-venue-contract", label: "Sign venue contract", done: true },
        { id: "task-walkthrough", label: "Schedule final walkthrough", done: true },
      ],
    },
    {
      name: "Food & beverage",
      owner: "Catering",
      tone: "green",
      tasks: [
        { id: "task-catering-quotes", label: "Collect 3 catering quotes", done: true },
        { id: "task-menu", label: "Finalize menu + dietary needs", done: false },
        { id: "task-catering-contract", label: "Sign catering contract", done: false },
      ],
    },
    {
      name: "Experience",
      owner: "Entertainment",
      tone: "amber",
      tasks: [
        { id: "task-book-dj", label: "Book DJ / entertainment", done: false },
        { id: "task-av", label: "Confirm A/V + staging", done: true },
        { id: "task-run-of-show", label: "Plan run-of-show", done: false },
      ],
    },
    {
      name: "Brand & decor",
      owner: "Merch",
      tone: "gray",
      tasks: [
        { id: "task-merch-artwork", label: "Approve merch artwork", done: false },
        { id: "task-arrangements", label: "Source arrangements", done: false },
        { id: "task-signage", label: "Order signage", done: false },
      ],
    },
    {
      name: "People & logistics",
      owner: "Staffing",
      tone: "blue",
      tasks: [
        { id: "task-crew", label: "Hire event crew (12)", done: true },
        { id: "task-shifts", label: "Confirm staff shifts", done: true },
        { id: "task-permits", label: "File city permits", done: true },
      ],
    },
  ],
  risks: [
    {
      level: "Medium",
      title: "DJ not yet locked",
      mitigation:
        "Aug 6 is a popular Saturday-adjacent date. Deposit approval is pending; Foghorn DJs held as backup at $2,800.",
    },
    {
      level: "Medium",
      title: "Merch production is tight",
      mitigation:
        "12-day lead vs. an Aug 4 need. Expedited shipping approved keeps it on schedule with ~1 day of slack.",
    },
    {
      level: "Low",
      title: "Outdoor cocktail area",
      mitigation:
        "20% chance of rain in the forecast window. Tent rental pre-quoted at $600 and can be added within 48h.",
    },
  ],
  milestones: [
    { title: "Requirements captured", when: "Jul 2", done: true },
    { title: "Plan approved", when: "Jul 4", done: true },
    { title: "Venue booked", when: "Jul 8", done: true },
    { title: "Catering signed", when: "pending", done: false },
    { title: "Final headcount", when: "Aug 1", done: false },
    { title: "All vendors confirmed", when: "Aug 2", done: false },
  ],
};

// Category paid amounts sum to MOCK_DASHBOARD.budget.paidUsd ($22,100).
const MOCK_BUDGET_DETAIL: BudgetDetail = {
  categories: [
    { name: "Venue", committedUsd: 24_000, paidUsd: 12_000 },
    { name: "Catering", committedUsd: 18_400, paidUsd: 0 },
    { name: "A/V + staging", committedUsd: 9_600, paidUsd: 2_400 },
    { name: "Rentals", committedUsd: 6_100, paidUsd: 6_100 },
    { name: "Staffing", committedUsd: 5_200, paidUsd: 0 },
    { name: "Decorations", committedUsd: 4_000, paidUsd: 0, estimate: true },
    { name: "Photography", committedUsd: 3_400, paidUsd: 950 },
    { name: "Entertainment", committedUsd: 3_200, paidUsd: 0 },
    { name: "Merchandise", committedUsd: 2_940, paidUsd: 0 },
    { name: "Signage", committedUsd: 1_800, paidUsd: 0, estimate: true },
    { name: "Permits", committedUsd: 650, paidUsd: 650 },
  ],
  savings: [
    {
      title: "Bundle rentals with venue",
      amount: "−$490",
      note: "Pier 27 gives 8% off tables and linens when booked with the space.",
    },
    {
      title: "Sign catering by Jul 30",
      amount: "−$920",
      note: "Bi-Rite waives the 8% service fee for an early signature.",
    },
    {
      title: "Switch to Foghorn DJs",
      amount: "−$400",
      note: "Similar 4.8★ reviews at $2,800. Only if you'd rather not stretch the entertainment line.",
    },
  ],
  savingsFootnote:
    "Applying all three keeps you $2,810 under budget with a healthy contingency for day-of surprises.",
};

const MOCK_CALENDAR_EVENTS: CalendarEventItem[] = [
  { date: "2026-07-29", title: "DJ deposit due", kind: "warn" },
  { date: "2026-08-01", title: "Headcount due", kind: "warn" },
  { date: "2026-08-02", title: "Merch artwork", kind: "info" },
  { date: "2026-08-03", title: "Tasting call · 2 PM", kind: "info" },
  { date: "2026-08-04", title: "Walkthrough · 10 AM", kind: "info" },
  { date: "2026-08-04", title: "Venue payment", kind: "warn" },
  { date: "2026-08-05", title: "Rehearsal · 4 PM", kind: "info" },
  { date: "2026-08-06", title: "★ Event day", kind: "accent" },
  { date: "2026-08-07", title: "Vendor payouts", kind: "info" },
  { date: "2026-08-07", title: "Teardown", kind: "muted" },
];

const MOCK_AGENDA: DeadlineItem[] = [
  { id: "agenda-dj-deposit", month: "Jul", day: "29", title: "DJ deposit due", meta: "Marina Sound · $1,600", emphasis: "urgent" },
  { id: "agenda-headcount", month: "Aug", day: "01", title: "Final headcount to caterer", meta: "Bi-Rite" },
  { id: "agenda-tasting", month: "Aug", day: "03", title: "Catering tasting call", meta: "2:00 PM · video" },
  { id: "agenda-walkthrough", month: "Aug", day: "04", title: "Venue walkthrough + payment", meta: "10 AM · $12,000 due" },
  { id: "agenda-rehearsal", month: "Aug", day: "05", title: "Rehearsal & setup", meta: "4:00 PM at Pier 27" },
  { id: "agenda-event-day", month: "Aug", day: "06", title: "Event day", meta: "Load-in 8 AM · doors 7 PM", emphasis: "event" },
];

const MOCK_DEADLINES: DeadlineItem[] = [
  { id: "deadline-dj-deposit", month: "Jul", day: "29", title: "DJ deposit due", meta: "Marina Sound · $1,600", emphasis: "urgent" },
  { id: "deadline-headcount", month: "Aug", day: "01", title: "Final headcount to caterer", meta: "Bi-Rite · lock guest count" },
  { id: "deadline-artwork", month: "Aug", day: "02", title: "Merch artwork approval", meta: "4imprint · print-ready deadline" },
  { id: "deadline-venue-payment", month: "Aug", day: "04", title: "Venue final payment", meta: "Pier 27 · $12,000" },
  { id: "deadline-event-day", month: "Aug", day: "06", title: "Event day", meta: "Load-in 8:00 AM", emphasis: "event" },
];

const MOCK_DECISIONS: DecisionRecord[] = [
  { id: "decision-pier27", title: "Pier 27 venue deposit", amount: "$12,000", when: "2d ago", approved: true },
  { id: "decision-stagecraft", title: "StageCraft A/V — 50% deposit", amount: "$4,800", when: "3d ago", approved: true },
  { id: "decision-rentals", title: "Standard Party Rentals", amount: "$6,100", when: "3d ago", approved: true },
  { id: "decision-foghorn", title: "Foghorn DJs (declined for Marina)", amount: "$2,800", when: "4d ago", approved: false },
  { id: "decision-lumen", title: "Lumen Studio deposit", amount: "$1,700", when: "5d ago", approved: true },
];

const MOCK_SPENDING_RULES: SpendingRule[] = [
  { id: "rule-purchases", label: "Purchases under the limit", value: "Auto" },
  { id: "rule-contracts", label: "Vendor contracts", value: "Ask first" },
  { id: "rule-deposits", label: "Deposits & payments", value: "Ask first" },
  { id: "rule-emails", label: "Sending emails", value: "Auto" },
  { id: "rule-private-data", label: "Sharing private data", value: "Ask first" },
];

const MOCK_POST_EVENT_TASKS: PostEventTask[] = [
  {
    id: "post-pay-vendors",
    glyph: "$",
    title: "Pay outstanding vendors",
    description: "Release final balances to 11 vendors per contract terms.",
    state: "Scheduled",
  },
  {
    id: "post-thank-you",
    glyph: "✉",
    title: "Send thank-you emails",
    description: "Personalized notes to vendors and speakers.",
    state: "Draft ready",
  },
  {
    id: "post-survey",
    glyph: "★",
    title: "Run attendee feedback survey",
    description: "3-question NPS survey to 320 guests.",
    state: "Draft ready",
  },
  {
    id: "post-reconcile",
    glyph: "∑",
    title: "Reconcile the budget",
    description: "Match receipts, flag variances, close the ledger.",
    state: "Scheduled",
  },
  {
    id: "post-refunds",
    glyph: "↻",
    title: "Request eligible refunds",
    description: "Unused rentals and the weather-tent deposit.",
    state: "Scheduled",
  },
  {
    id: "post-photos",
    glyph: "▣",
    title: "Collect photos & video",
    description: "Gather deliverables from Lumen Studio into a shared album.",
    state: "Scheduled",
  },
];

const MOCK_ACTIVITY_POOL: ActivityItem[] = [
  {
    id: "pool-totes",
    agent: "Purchasing",
    tone: "blue",
    timeAgo: "just now",
    description: "Compared 3 tote suppliers; 4imprint is cheapest at $8.40 per unit.",
  },
  {
    id: "pool-gluten-free",
    agent: "Catering",
    tone: "blue",
    timeAgo: "just now",
    description: "Bi-Rite replied — they can accommodate all 22 gluten-free guests.",
  },
  {
    id: "pool-servers",
    agent: "Staffing",
    tone: "green",
    timeAgo: "just now",
    description: "Confirmed 12 servers with OnCall Events for the Aug 6 shift.",
  },
  {
    id: "pool-crosspost",
    agent: "Distribution",
    tone: "blue",
    timeAgo: "just now",
    description: "Cross-posted the event to Partiful and Eventbrite.",
  },
  {
    id: "pool-coi",
    agent: "Venue",
    tone: "green",
    timeAgo: "just now",
    description: "Filed the signed Pier 27 certificate of insurance to records.",
  },
  {
    id: "pool-dj-hold",
    agent: "Entertainment",
    tone: "amber",
    timeAgo: "just now",
    description: "Marina Sound is holding Aug 6, pending your deposit approval.",
  },
  {
    id: "pool-arrangements",
    agent: "Decorations",
    tone: "blue",
    timeAgo: "just now",
    description: "Sourced 8 arrangement options from Bloom & Co within budget.",
  },
  {
    id: "pool-calendar-sync",
    agent: "Scheduling",
    tone: "blue",
    timeAgo: "just now",
    description: "Synced 6 vendor calendar holds and resolved a load-in conflict.",
  },
];
