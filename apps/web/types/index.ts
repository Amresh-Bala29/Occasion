// Shared front-end types for the Occasion web app.
export type EventStatus = "draft" | "planning" | "confirmed" | "completed";

export interface EventSummary {
  id: string;
  name: string;
  status: EventStatus;
}

/** Visual accent used for agent dots, labels, and activity icons. */
export type Tone = "green" | "blue" | "amber" | "gray";

/** The active event as shown in the overview header card. */
export interface EventOverview {
  id: string;
  kind: string; // e.g. "Company summit"
  name: string; // e.g. "NovaFlow Summit 2026"
  shortName: string; // sidebar selector label, e.g. "NovaFlow Summit"
  statusLabel: string; // e.g. "On track"
  date: string;
  location: string;
  headcount: string;
  daysToGo: string;
  percentComplete: number;
}

/** Budget totals in whole dollars; committed = paid + pending. */
export interface BudgetOverview {
  totalUsd: number;
  paidUsd: number;
  pendingUsd: number;
}

export interface VendorOverview {
  confirmed: number;
  total: number;
  inProgress: number;
}

/** One decision waiting on the organizer. */
export interface ApprovalItem {
  id: string;
  kind: string; // "Purchase" | "Booking" | "Contract"
  agent: string; // e.g. "Purchasing agent"
  agentTone: Tone;
  tag: string; // e.g. "Over limit"
  title: string;
  description: string;
  amount: string; // preformatted, e.g. "$2,940"
  vendor: string;
  threadId?: string; // inbox conversation behind "View thread"
}

export interface AgentStatus {
  name: string;
  tone: Tone;
  status: string;
}

export interface ActivityItem {
  id: string;
  agent: string;
  tone: Tone;
  timeAgo: string;
  description: string;
}

/** Everything the overview dashboard renders. */
export interface DashboardData {
  event: EventOverview;
  budget: BudgetOverview;
  vendors: VendorOverview;
  approvals: ApprovalItem[];
  agents: AgentStatus[];
  activity: ActivityItem[];
  agentsWorking: number;
  messagesCount: number;
  autoApproveLimit: string; // preformatted, e.g. "$500"
}

// ---- Vendors tab ----

export type VendorStatus = "Confirmed" | "Awaiting you" | "Negotiating" | "Sourcing";

export interface Vendor {
  id: string;
  initials: string; // avatar monogram, e.g. "P27"
  name: string;
  category: string;
  status: VendorStatus;
  quotes: number;
  lastActivity: string; // e.g. "2h ago"
  cost: string; // preformatted; a "~" prefix marks an estimate
}

// ---- Plan tab ----

export interface PlanPhase {
  name: string;
  percent: number; // 0–100
  note: string; // e.g. "Done", "3 of 4", "Aug 6"
}

export interface PlanTask {
  id: string;
  label: string;
  done: boolean;
}

export interface PlanTaskGroup {
  name: string;
  owner: string; // agent responsible for the group, e.g. "Venue"
  tone: Tone;
  tasks: PlanTask[];
}

export interface RiskItem {
  level: "Low" | "Medium" | "High";
  title: string;
  mitigation: string;
}

export interface Milestone {
  title: string;
  when: string; // e.g. "Jul 2" or "pending"
  done: boolean;
}

export interface EventPlan {
  phases: PlanPhase[];
  groups: PlanTaskGroup[];
  risks: RiskItem[];
  milestones: Milestone[];
}

// ---- Budget tab ----

export interface BudgetCategory {
  name: string;
  committedUsd: number;
  paidUsd: number;
  estimate?: boolean; // still sourcing; committed is a projection
}

export interface SavingSuggestion {
  title: string;
  amount: string; // preformatted, e.g. "−$490"
  note: string;
}

export interface BudgetDetail {
  categories: BudgetCategory[];
  savings: SavingSuggestion[];
  savingsFootnote: string;
}

// ---- Calendar tab and deadline lists ----

export type CalendarEventKind = "warn" | "info" | "accent" | "muted";

export interface CalendarEventItem {
  date: string; // ISO day, e.g. "2026-08-06"
  title: string;
  kind: CalendarEventKind;
}

/** One row in a date-led list (overview deadlines, calendar agenda). */
export interface DeadlineItem {
  id: string;
  month: string; // "Jul"
  day: string; // "29"
  title: string;
  meta: string;
  emphasis?: "urgent" | "event";
}

// ---- Approvals tab ----

export interface DecisionRecord {
  id: string;
  title: string;
  amount: string;
  when: string; // e.g. "2d ago"
  approved: boolean;
}

export interface SpendingRule {
  id: string;
  label: string;
  value: "Auto" | "Ask first";
}

// ---- Post-event tab ----

export interface PostEventTask {
  id: string;
  glyph: string; // small icon glyph, e.g. "$"
  title: string;
  description: string;
  state: "Scheduled" | "Draft ready";
}

// ---- Unified inbox (Messages tab) ----

export type InboxFilter = "all" | "unread" | "archived";

/** One message inside a conversation thread. */
export interface InboxMessage {
  id: string;
  author: string; // display name; outgoing messages use "You"
  fromMe?: boolean;
  day: string; // thread separator label, e.g. "Thu, Jul 9"
  time: string; // e.g. "3:16 PM"
  body: string; // paragraphs separated by blank lines
}

/** One thread in the unified inbox, aggregated from any channel. */
export interface Conversation {
  id: string;
  name: string;
  subtitle: string; // e.g. "Venue manager · Pier 27"
  channel: string; // where it came from, e.g. "Email", "Vendor portal"
  avatarInitials: string;
  timeLabel: string; // list column label, e.g. "Jul 9"
  preview: string;
  unread: boolean;
  archived: boolean;
  quickReplies: string[];
  messages: InboxMessage[];
}

/** One turn in the Plan chat. Assistant turns that ran a browser task carry the session result. */
export interface PlanChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string; // ISO timestamp
  result?: SessionResult;
  isError?: boolean;
}

// ---- Agent service (mirrors services/agent/integrations/h_company/schemas.py) ----

export interface ComputerUseRequest {
  task: string;
  agent?: string;
}

/** Honest result of one computer-use session; branch on `succeeded`. */
export interface SessionResult {
  succeeded: boolean;
  status: string; // completed | failed | timed_out | interrupted | idle | error
  outcome: string | null; // success | partial | infeasible | blocked
  answer: string | null;
  error: string | null;
  session_id: string | null;
  agent_view_url: string | null;
}
