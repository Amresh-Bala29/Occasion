// API layer for the Occasion web app. Components call these functions instead
// of fetch()ing directly so backend wiring stays in one place.
import type {
  ActivityItem,
  AgentRunRecord,
  BudgetDetail,
  CalendarEventItem,
  Conversation,
  DashboardData,
  DeadlineItem,
  DecisionRecord,
  EventOverview,
  EventPlan,
  EventSessionsReport,
  PostEventTask,
  SpendingRule,
  TranscriptionResult,
  Vendor,
} from "@/types";

const AGENT_URL = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000";
// In containers the server-side origin differs from the browser's (SSR reaches the
// agent over the compose network); AGENT_INTERNAL_URL overrides it there only.
const SERVER_AGENT_URL = process.env.AGENT_INTERNAL_URL ?? AGENT_URL;

function baseUrl(): string {
  return typeof window === "undefined" ? SERVER_AGENT_URL : AGENT_URL;
}

/** The demo event, used when no active-event cookie is set. */
export const DEFAULT_EVENT_ID = "novaflow-summit-2026";

/** Cookie holding the active event id; set by the sidebar switcher, read by server pages. */
export const EVENT_COOKIE = "occasion_event";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    // no-store keeps reads as fresh as the mock getters were.
    response = await fetch(`${baseUrl()}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new Error(`Could not reach the agent service at ${baseUrl()}. Is it running?`);
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
 * Send one conversational turn to the orchestrator. The run starts in the
 * background and this resolves immediately with its `running` record; follow up
 * with awaitRun (or getRun) until it settles — browser tasks can take minutes.
 */
export function sendChatMessage(message: string, eventId: string | null): Promise<AgentRunRecord> {
  return sendJson<AgentRunRecord>("/chat", "POST", { message, event_id: eventId });
}

/** One background run's current state. */
export function getRun(runId: string): Promise<AgentRunRecord> {
  return request<AgentRunRecord>(`/runs/${runId}`);
}

const RUN_POLL_MS = 2500;

/** Poll a run until it settles; tolerates brief agent-service blips mid-poll. */
export async function awaitRun(runId: string): Promise<AgentRunRecord> {
  let misses = 0;
  for (;;) {
    try {
      const run = await getRun(runId);
      misses = 0;
      if (run.status !== "running") return run;
    } catch (error) {
      if (++misses >= 3) throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, RUN_POLL_MS));
  }
}

/** Every event in the workspace, for the sidebar switcher. */
export function getEvents(): Promise<EventOverview[]> {
  return request<EventOverview[]>("/events");
}

/** Live H browser sessions for the event; the agent rail polls this. */
export function getAgentSessions(eventId: string): Promise<EventSessionsReport> {
  return request<EventSessionsReport>(`/events/${eventId}/agent-sessions`);
}

/** The real activity feed — what agents actually did — newest first. */
export function getActivity(eventId: string): Promise<ActivityItem[]> {
  return request<ActivityItem[]>(`/events/${eventId}/activity`);
}

/** Turn one recorded voice clip into text; the blob's type rides as Content-Type. */
export function transcribeAudio(audio: Blob): Promise<TranscriptionResult> {
  return request<TranscriptionResult>("/voice/transcribe", {
    method: "POST",
    headers: { "Content-Type": audio.type || "audio/wav" },
    body: audio,
  });
}

/** Synthesize speech for an answer; resolves to a playable audio blob. */
export async function speak(text: string): Promise<Blob> {
  // Mirrors request(): same error shaping, but the success body is bytes, not JSON.
  let response: Response;
  try {
    response = await fetch(`${AGENT_URL}/voice/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  } catch {
    throw new Error(`Could not reach the agent service at ${AGENT_URL}. Is it running?`);
  }
  if (!response.ok) {
    throw new Error(`Agent service returned ${response.status}: ${await readErrorDetail(response)}`);
  }
  return response.blob();
}

/** Everything the overview dashboard renders for the active event. */
export function getDashboardData(eventId: string = DEFAULT_EVENT_ID): Promise<DashboardData> {
  return request<DashboardData>(`/events/${eventId}/dashboard`);
}

/** Every inbox thread on the event; the messages panel filters this list. */
export function getInboxConversations(eventId: string = DEFAULT_EVENT_ID): Promise<Conversation[]> {
  return request<Conversation[]>(`/events/${eventId}/conversations`);
}

/** Every vendor on the event; the vendors panel filters this list by status. */
export function getVendors(eventId: string = DEFAULT_EVENT_ID): Promise<Vendor[]> {
  return request<Vendor[]>(`/events/${eventId}/vendors`);
}

/** Phases, task checklist, risks, and milestones for the plan board. */
export function getEventPlan(eventId: string = DEFAULT_EVENT_ID): Promise<EventPlan> {
  return request<EventPlan>(`/events/${eventId}/plan`);
}

/** Per-category spend and suggested savings for the budget panel. */
export function getBudgetDetail(eventId: string = DEFAULT_EVENT_ID): Promise<BudgetDetail> {
  return request<BudgetDetail>(`/events/${eventId}/budget`);
}

/** Dated items rendered on the calendar month grid. */
export function getCalendarEvents(eventId: string = DEFAULT_EVENT_ID): Promise<CalendarEventItem[]> {
  return request<CalendarEventItem[]>(`/events/${eventId}/calendar`);
}

/** The "Upcoming" rail beside the calendar. */
export function getCalendarAgenda(eventId: string = DEFAULT_EVENT_ID): Promise<DeadlineItem[]> {
  return request<DeadlineItem[]>(`/events/${eventId}/agenda`);
}

/** The short deadline list on the overview page. */
export function getKeyDeadlines(eventId: string = DEFAULT_EVENT_ID): Promise<DeadlineItem[]> {
  return request<DeadlineItem[]>(`/events/${eventId}/deadlines`);
}

/** Already-decided approvals shown under "Recent decisions". */
export function getDecisionHistory(eventId: string = DEFAULT_EVENT_ID): Promise<DecisionRecord[]> {
  return request<DecisionRecord[]>(`/events/${eventId}/decisions`);
}

/** Which action classes run automatically vs. pause for sign-off. */
export function getSpendingRules(eventId: string = DEFAULT_EVENT_ID): Promise<SpendingRule[]> {
  return request<SpendingRule[]>(`/events/${eventId}/spending-rules`);
}

/** Wrap-up work queued to run automatically after the event. */
export function getPostEventTasks(eventId: string = DEFAULT_EVENT_ID): Promise<PostEventTask[]> {
  return request<PostEventTask[]>(`/events/${eventId}/post-event-tasks`);
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
