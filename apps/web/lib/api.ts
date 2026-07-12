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

// One demo event until multi-event support lands; every getter scopes to it.
export const DEFAULT_EVENT_ID = "novaflow-summit-2026";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    // no-store keeps reads as fresh as the mock getters were.
    response = await fetch(`${AGENT_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new Error(`Could not reach the agent service at ${AGENT_URL}. Is it running?`);
  }
  if (!response.ok) {
    throw new Error(`Agent service returned ${response.status}: ${await readErrorDetail(response)}`);
  }
  return (await response.json()) as T;
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
  } catch {
    return response.statusText || "unknown error";
  }
}

function sendJson<T>(path: string, method: "POST" | "PUT", body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * Run one natural-language browser task through the agent service.
 * The request blocks until the session settles, which can take a few minutes.
 */
export function runComputerUseTask(task: string): Promise<SessionResult> {
  return sendJson<SessionResult>("/api/computer-use/run", "POST", { task });
}

/** Everything the overview dashboard renders for the active event. */
export function getDashboardData(): Promise<DashboardData> {
  return request<DashboardData>(`/events/${DEFAULT_EVENT_ID}/dashboard`);
}

/** Every inbox thread on the event; the messages panel filters this list. */
export function getInboxConversations(): Promise<Conversation[]> {
  return request<Conversation[]>(`/events/${DEFAULT_EVENT_ID}/conversations`);
}

/** Every vendor on the event; the vendors panel filters this list by status. */
export function getVendors(): Promise<Vendor[]> {
  return request<Vendor[]>(`/events/${DEFAULT_EVENT_ID}/vendors`);
}

/** Phases, task checklist, risks, and milestones for the plan board. */
export function getEventPlan(): Promise<EventPlan> {
  return request<EventPlan>(`/events/${DEFAULT_EVENT_ID}/plan`);
}

/** Per-category spend and suggested savings for the budget panel. */
export function getBudgetDetail(): Promise<BudgetDetail> {
  return request<BudgetDetail>(`/events/${DEFAULT_EVENT_ID}/budget`);
}

/** Dated items rendered on the calendar month grid. */
export function getCalendarEvents(): Promise<CalendarEventItem[]> {
  return request<CalendarEventItem[]>(`/events/${DEFAULT_EVENT_ID}/calendar`);
}

/** The "Upcoming" rail beside the calendar. */
export function getCalendarAgenda(): Promise<DeadlineItem[]> {
  return request<DeadlineItem[]>(`/events/${DEFAULT_EVENT_ID}/agenda`);
}

/** The short deadline list on the overview page. */
export function getKeyDeadlines(): Promise<DeadlineItem[]> {
  return request<DeadlineItem[]>(`/events/${DEFAULT_EVENT_ID}/deadlines`);
}

/** Already-decided approvals shown under "Recent decisions". */
export function getDecisionHistory(): Promise<DecisionRecord[]> {
  return request<DecisionRecord[]>(`/events/${DEFAULT_EVENT_ID}/decisions`);
}

/** Which action classes run automatically vs. pause for sign-off. */
export function getSpendingRules(): Promise<SpendingRule[]> {
  return request<SpendingRule[]>(`/events/${DEFAULT_EVENT_ID}/spending-rules`);
}

/** Wrap-up work queued to run automatically after the event. */
export function getPostEventTasks(): Promise<PostEventTask[]> {
  return request<PostEventTask[]>(`/events/${DEFAULT_EVENT_ID}/post-event-tasks`);
}

/** Rotating pool of simulated agent updates that feed the live activity rail. */
export function getActivityPool(): Promise<ActivityItem[]> {
  return request<ActivityItem[]>(`/events/${DEFAULT_EVENT_ID}/activity-pool`);
}

/** Resolve a pending approval; returns the recorded decision. */
export function resolveApproval(approvalId: string, approved: boolean): Promise<DecisionRecord> {
  return sendJson<DecisionRecord>(`/approvals/${approvalId}`, "POST", { approved });
}

/** Flip a spending rule between "Auto" and "Ask first"; returns the updated rule. */
export function toggleSpendingRule(eventId: string, ruleId: string): Promise<SpendingRule> {
  return sendJson<SpendingRule>(`/events/${eventId}/spending-rules/${ruleId}`, "POST", {});
}

/** Persist the auto-approve limit (a preformatted string like "$500"). */
export async function saveAutoApproveLimit(eventId: string, limit: string): Promise<void> {
  await sendJson<{ autoApproveLimit: string }>(`/events/${eventId}/auto-approve-limit`, "PUT", { limit });
}
