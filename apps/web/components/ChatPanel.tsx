"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { VoiceAssistant } from "@/components/VoiceAssistant";
import { useAgentStream, isProgressing, type AgentStreamState } from "@/hooks/useAgentStream";
import { awaitRun, getEventRuns, getSessionFrame, sendChatMessage } from "@/lib/api";
import type { AgentRunRecord, AgentSessionSummary, ChatMessage, SessionFrame } from "@/types";

type ChatMode = "intake" | "workspace";

interface ChatPanelProps {
  eventId: string;
  mode: ChatMode;
  /**
   * Intake only: fired exactly once, when a turn settles with no open questions left.
   * Receives the captured brief so the caller can persist it onto the event.
   */
  onIntakeComplete?: (requirements: RequirementsData) => void;
}

const SUGGESTIONS = [
  "Find three caterers near Pier 27 in San Francisco that can serve 320 guests on Aug 6",
  "Compare DJs available on Aug 6 under $3,500 with strong reviews",
  "Research custom tote bag suppliers that can deliver 350 units by Aug 4",
];

/** What the requirements agent returns in `result.data` (mirror of EventRequirements). */
export interface RequirementsData {
  event_type?: string | null;
  date?: string | null;
  duration?: string | null;
  location?: string | null;
  venue_preferences?: string | null;
  headcount?: number | null;
  budget_usd?: number | null;
  priorities?: string[];
  open_questions?: string[];
}

/**
 * The Occasion chat: each prompt runs as a real agent task and the result lands
 * back in the thread. History persists locally per event, shared across both
 * surfaces. `intake` mode pins the requirements agent and drives the interview;
 * `workspace` mode routes freely across the fleet.
 */
export function ChatPanel({ eventId, mode, onIntakeComplete }: ChatPanelProps) {
  // Keys predate this component (they shipped with the Plan chat); keeping them
  // preserves existing threads. Two tabs on the same event share them — both may
  // append the same settled turn (last writer wins). Accepted for a polled chat.
  const storageKey = `occasion:plan-chat:${eventId}`;
  const pendingKey = `occasion:plan-chat-pending:${eventId}`;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [clearArmed, setClearArmed] = useState(false);
  const [interviewDone, setInterviewDone] = useState(false);
  // True from the moment the intake transition fires until the page navigates away.
  const [locked, setLocked] = useState(false);
  const completeFiredRef = useRef(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const threadEndRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  // Workspace polls for the whole visit so the live grid also covers background
  // runs (approved bookings); intake keeps the pending gate — its turns are browserless.
  const stream = useAgentStream(eventId, mode === "workspace" || pending);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // Async appends write straight through to storage: a run that settles after
  // the user navigates to another section still lands in the thread they return to
  // (the unmounted setMessages alone would silently drop it).
  function appendMessage(message: ChatMessage) {
    const next = [...messagesRef.current, message];
    messagesRef.current = next;
    setMessages(next);
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      // Storage full or blocked; the chat still works for this visit.
    }
  }

  // A thread that already finished the interview must not re-trigger the
  // intake transition on a later visit — offer the inline link instead.
  function noteInterviewState(thread: ChatMessage[]) {
    if (thread.some((message) => message.questions?.length === 0)) {
      completeFiredRef.current = true;
      setInterviewDone(true);
    }
  }

  // Restore the conversation once on mount; only persist after that restore.
  // Local storage is the fast path; when it's empty the thread is rebuilt from the
  // durable run log in the agent's database, so a project's conversation survives
  // new browsers and cleared storage.
  useEffect(() => {
    let cancelled = false;
    try {
      const stored = window.localStorage.getItem(storageKey);
      if (stored) {
        const parsed = JSON.parse(stored) as ChatMessage[];
        setMessages(parsed);
        noteInterviewState(parsed);
        setHydrated(true);
        return;
      }
    } catch {
      // Corrupt or unavailable storage; fall through to the server log.
    }
    getEventRuns(eventId)
      .then((runs) => {
        // A turn the user already started locally outranks the fetched snapshot.
        if (cancelled || messagesRef.current.length > 0) return;
        const restored = runs
          .filter((run) => run.status !== "running")
          .flatMap((run) => threadTurns(run, mode));
        if (restored.length === 0) return;
        messagesRef.current = restored;
        setMessages(restored);
        noteInterviewState(restored);
      })
      .catch(() => {
        // Agent service unreachable: start blank; the first turn surfaces the outage.
      })
      .finally(() => {
        if (!cancelled) setHydrated(true);
      });
    return () => {
      cancelled = true;
    };
    // mode and the interview-state setter are stable for the component's lifetime.
  }, [storageKey, eventId]);

  // A turn interrupted by a reload keeps running server-side; pick its poll back up.
  useEffect(() => {
    const pendingRunId = window.localStorage.getItem(pendingKey);
    if (!pendingRunId) return;
    setPending(true);
    awaitRun(pendingRunId)
      .then((run) => {
        appendMessage(toChatMessage(run, mode));
        maybeFireComplete(run);
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error);
        appendMessage({ ...newMessage("assistant", message), isError: true });
      })
      .finally(() => {
        window.localStorage.removeItem(pendingKey);
        setPending(false);
      });
    // mode and the completion callback are stable for the component's lifetime.
  }, [pendingKey]);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(messages));
    } catch {
      // Storage full or blocked; the chat still works for this visit.
    }
  }, [messages, hydrated, storageKey]);

  useEffect(() => {
    if (messages.length === 0 && !pending) return;
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending]);

  function maybeFireComplete(run: AgentRunRecord) {
    const requirements = requirementsData(run);
    if (!requirements || (requirements.open_questions ?? []).length > 0) return;
    setInterviewDone(true);
    if (mode !== "intake" || completeFiredRef.current) return;
    completeFiredRef.current = true;
    setLocked(true); // composer stays down while the hero fades out
    onIntakeComplete?.(requirements);
  }

  async function send(text: string) {
    const prompt = text.trim();
    if (!prompt || pending || locked) return;
    setDraft("");
    setClearArmed(false);
    // The requirements agent extracts from the whole conversation, so intake
    // turns resend the accumulated transcript rather than just this message.
    const wire = mode === "intake" ? buildTranscript(messages, prompt) : prompt;
    appendMessage(newMessage("user", prompt));
    setPending(true);
    try {
      const started = await sendChatMessage(wire, eventId, mode === "intake" ? "requirements" : undefined);
      // Remember the in-flight run so a reload resumes the poll instead of losing it.
      window.localStorage.setItem(pendingKey, started.id);
      const settled = await awaitRun(started.id);
      appendMessage(toChatMessage(settled, mode));
      maybeFireComplete(settled);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      appendMessage({ ...newMessage("assistant", message), isError: true });
    } finally {
      window.localStorage.removeItem(pendingKey);
      setPending(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void send(draft);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send(draft);
    }
  }

  function appendTranscript(text: string) {
    setDraft((current) => (current ? `${current} ${text}` : text));
  }

  function pickSuggestion(suggestion: string) {
    setDraft(suggestion);
    composerRef.current?.focus();
  }

  function handleClearClick() {
    if (!clearArmed) {
      setClearArmed(true);
      return;
    }
    setMessages([]);
    setClearArmed(false);
  }

  const thread = (
    <>
      {messages.map((message) =>
        message.role === "user" ? (
          <UserBubble key={message.id} message={message} />
        ) : (
          <AssistantBubble key={message.id} message={message} />
        ),
      )}
      {pending && <ThinkingBubble stream={stream} intake={mode === "intake"} />}
      <div ref={threadEndRef} />
    </>
  );

  if (mode === "intake") {
    return (
      <div className="flex w-full flex-col gap-4">
        {(messages.length > 0 || pending) && (
          <div className="flex max-h-[46vh] flex-col gap-4 overflow-y-auto pr-1">{thread}</div>
        )}
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-2 rounded-[26px] border border-line bg-surface/90 p-3 shadow-modal backdrop-blur focus-within:border-brand"
        >
          <label className="sr-only" htmlFor="occasion-chat-input">
            Tell Occasion about your event
          </label>
          <textarea
            id="occasion-chat-input"
            ref={composerRef}
            rows={2}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            disabled={locked}
            placeholder="Tell me about your event — type, date, city, headcount, budget…"
            className="max-h-48 min-h-[56px] w-full resize-none bg-transparent px-2 py-1.5 text-[15px] leading-relaxed outline-none [field-sizing:content] placeholder:text-ink-faint"
          />
          <div className="flex items-center justify-end gap-2">
            <VoiceAssistant onTranscript={appendTranscript} />
            <button
              type="submit"
              aria-label="Send"
              disabled={!draft.trim() || pending || locked}
              className="grid size-10 shrink-0 cursor-pointer place-items-center rounded-full bg-brand text-white hover:bg-brand-deep disabled:cursor-default disabled:opacity-40"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path
                  d="M8 13V3M8 3 3.5 7.5M8 3l4.5 4.5"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </div>
        </form>
        {interviewDone && !locked && (
          <p className="text-center">
            <Link
              href="/dashboard/ask"
              className="text-[13.5px] font-semibold text-brand hover:underline"
            >
              Continue to your dashboard →
            </Link>
          </p>
        )}
      </div>
    );
  }

  const showEmptyState = hydrated && messages.length === 0 && !pending;

  return (
    <main className="mx-auto flex w-full max-w-[860px] flex-1 flex-col px-6">
      <LiveBrowserGrid eventId={eventId} stream={stream} />
      <div className="flex flex-1 flex-col">
        {showEmptyState ? (
          <EmptyState onPick={pickSuggestion} />
        ) : (
          <>
            {messages.length > 0 && (
              <div className="flex justify-end pt-3">
                <button
                  type="button"
                  onClick={handleClearClick}
                  onBlur={() => setClearArmed(false)}
                  className="cursor-pointer text-[12px] text-ink-faint hover:text-ink hover:underline"
                >
                  {clearArmed ? "Click again to clear the conversation" : "Clear conversation"}
                </button>
              </div>
            )}
            <div className="flex flex-col gap-4 pt-4 pb-2">{thread}</div>
          </>
        )}
      </div>

      <div className="sticky bottom-0 bg-canvas pt-2 pb-5">
        <form
          onSubmit={handleSubmit}
          className="card flex items-end gap-2 rounded-2xl p-2 focus-within:border-brand"
        >
          <label className="sr-only" htmlFor="occasion-chat-input">
            Message Occasion
          </label>
          <textarea
            id="occasion-chat-input"
            ref={composerRef}
            rows={1}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            placeholder="Ask Occasion to research, compare, or plan…"
            className="max-h-40 min-h-[40px] w-full flex-1 resize-none bg-transparent px-2.5 py-2 text-[13.5px] leading-normal outline-none [field-sizing:content] placeholder:text-ink-faint"
          />
          <VoiceAssistant onTranscript={appendTranscript} />
          <button type="submit" className="btn btn-primary rounded-xl" disabled={!draft.trim() || pending}>
            Send
          </button>
        </form>
        <p className="mt-2 text-center text-[11px] text-ink-faint">
          Occasion works in a managed browser session. Sensitive actions still need your approval.
        </p>
      </div>
    </main>
  );
}

function newMessage(role: ChatMessage["role"], content: string): ChatMessage {
  return { id: crypto.randomUUID(), role, content, createdAt: new Date().toISOString() };
}

/** The requirements payload of a settled run, or null when this wasn't a clean requirements turn. */
function requirementsData(run: AgentRunRecord): RequirementsData | null {
  if (run.agent !== "requirements" || !run.result?.succeeded || !run.result.data) return null;
  return run.result.data as RequirementsData;
}

/**
 * The transcript an intake turn sends: what the client said and what Occasion
 * asked, in order. Other assistant turns (research results, errors) aren't client
 * requirements, so they stay out. Rebuilt from history, so reloads cost nothing.
 */
function buildTranscript(history: ChatMessage[], prompt: string): string {
  const lines: string[] = [];
  for (const message of history) {
    if (message.role === "user") {
      lines.push(`Client: ${message.content}`);
    } else if (message.questions && message.questions.length > 0) {
      lines.push(`Occasion asked: ${message.questions.join(" | ")}`);
    }
  }
  lines.push(`Client: ${prompt}`);
  return lines.join("\n");
}

/**
 * A settled run replayed as thread turns: the user's ask, then the assistant's
 * reply. Intake turns store the whole running transcript as the run title, so the
 * ask is its last "Client:" line; every other title is the ask verbatim.
 */
function threadTurns(run: AgentRunRecord, mode: ChatMode): ChatMessage[] {
  const asked = newMessage("user", lastClientLine(run.title));
  if (run.created_at) asked.createdAt = run.created_at;
  return [asked, toChatMessage(run, mode)];
}

function lastClientLine(title: string): string {
  const clientLines = title.split("\n").filter((line) => line.startsWith("Client: "));
  if (clientLines.length === 0) return title;
  return clientLines[clientLines.length - 1].slice("Client: ".length);
}

function toChatMessage(run: AgentRunRecord, mode: ChatMode): ChatMessage {
  const requirements = requirementsData(run);
  if (requirements) {
    // Requirements turns render from `data` — `answer` is the raw JSON string the
    // structured completion produced, never meant for the thread.
    const open = requirements.open_questions ?? [];
    if (open.length > 0) {
      const numbered = open.map((question, index) => `${index + 1}. ${question}`).join("\n");
      return {
        ...newMessage("assistant", `Noted. To finish your brief, could you tell me:\n${numbered}`),
        questions: open,
      };
    }
    const summary = requirementsSummary(requirements);
    const closing =
      mode === "intake" ? "That's everything I need — opening your dashboard…" : "Your brief is complete.";
    return {
      ...newMessage("assistant", summary ? `${summary}\n\n${closing}` : closing),
      questions: [],
    };
  }

  const result = run.result ?? undefined;
  const content =
    result?.answer ??
    result?.error ??
    (run.status === "interrupted"
      ? "This run was interrupted by a service restart."
      : "The run finished without an answer.");
  return {
    ...newMessage("assistant", content),
    result,
    routedAgent: run.agent,
    routedReason: run.reason,
    isError: !(result?.succeeded ?? false),
  };
}

function requirementsSummary(data: RequirementsData): string {
  const parts: string[] = [];
  if (data.event_type) parts.push(data.event_type);
  const when = [data.date, data.duration].filter(Boolean).join(", ");
  if (when) parts.push(when);
  if (data.location) parts.push(data.location);
  if (data.venue_preferences) parts.push(data.venue_preferences);
  if (data.headcount != null) parts.push(`${data.headcount} guests`);
  if (data.budget_usd != null) parts.push(`$${data.budget_usd.toLocaleString()} budget`);
  if (data.priorities && data.priorities.length > 0) parts.push(`priorities: ${data.priorities.join(", ")}`);
  return parts.length > 0 ? `Your brief: ${parts.join(" · ")}.` : "";
}

function EmptyState({ onPick }: { onPick: (suggestion: string) => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
      <span className="relative size-10 rounded-xl bg-brand" aria-hidden="true">
        <span className="absolute inset-3 rounded-full border-[3px] border-white" />
      </span>
      <h2 className="mt-1 font-serif text-[26px] font-medium">Plan with Occasion</h2>
      <p className="max-w-[46ch] text-[13.5px] leading-relaxed text-ink-soft">
        Describe what you need for the event and Occasion will go do the work on real websites —
        researching vendors, comparing quotes, and reporting back here.
      </p>
      <div className="mt-3 flex w-full max-w-[560px] flex-col gap-2">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            onClick={() => onPick(suggestion)}
            className="card cursor-pointer px-4 py-3 text-left text-[13px] text-ink-soft hover:border-brand hover:text-ink"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

function UserBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-[6px] bg-brand px-4 py-2.5 text-[13.5px] leading-relaxed break-words whitespace-pre-wrap text-white">
      {message.content}
    </div>
  );
}

function AssistantBubble({ message }: { message: ChatMessage }) {
  const result = message.result;
  const bubbleClasses = message.isError
    ? "border-[#f5c2c2] bg-danger-soft text-danger"
    : "border-line bg-surface";

  return (
    <div className="flex gap-2.5">
      <AssistantAvatar />
      <div className={`min-w-0 max-w-[92%] rounded-2xl rounded-bl-[6px] border px-4 py-3 shadow-card ${bubbleClasses}`}>
        {message.routedAgent && (
          <p className="mb-1.5 text-[11.5px] font-medium text-ink-faint">
            Routed to {message.routedAgent}
            {message.routedReason ? ` — ${message.routedReason}` : ""}
          </p>
        )}
        {result && (
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="chip chip-gray">{result.status}</span>
            {result.outcome && <span className={outcomeChipClass(result.outcome)}>{result.outcome}</span>}
            {result.agent_view_url && (
              <a
                className="ml-auto text-[12.5px] font-semibold whitespace-nowrap text-brand hover:underline"
                href={result.agent_view_url}
                target="_blank"
                rel="noreferrer"
              >
                Open agent view ↗
              </a>
            )}
          </div>
        )}
        <p className="text-[13.5px] leading-[1.6] break-words whitespace-pre-wrap">{message.content}</p>
        {result?.session_id && (
          <p className="mt-2 font-mono text-[10.5px] text-ink-faint [overflow-wrap:anywhere]">
            Session {result.session_id}
          </p>
        )}
      </div>
    </div>
  );
}

/** The live "thinking" bubble: honest polled signals, not invented thoughts. */
function ThinkingBubble({ stream, intake }: { stream: AgentStreamState; intake: boolean }) {
  const live = stream.report?.succeeded
    ? stream.report.sessions.filter((session) => isProgressing(session.status))
    : [];
  // The bubble mounts exactly for the pending turn, so its own clock is the
  // turn's stopwatch (the stream polls for the whole visit and can't time it).
  const [elapsedMs, setElapsedMs] = useState(0);
  useEffect(() => {
    const startedAt = Date.now();
    const clock = setInterval(() => setElapsedMs(Date.now() - startedAt), 1_000);
    return () => clearInterval(clock);
  }, []);

  return (
    <div className="flex gap-2.5" role="status">
      <AssistantAvatar />
      <div className="flex min-w-0 max-w-[92%] flex-col gap-2 rounded-2xl rounded-bl-[6px] border border-brand-mist bg-brand-soft px-4 py-3">
        <div className="flex items-center gap-3">
          <span
            className="size-4 shrink-0 animate-spin rounded-full border-2 border-brand-mist border-t-brand"
            aria-hidden="true"
          />
          <p className="text-[13px] leading-relaxed text-ink-soft">
            {live.length === 0
              ? quietLine(elapsedMs, intake)
              : `Working live in ${live.length === 1 ? "a managed browser" : `${live.length} managed browsers`} — ${formatElapsed(elapsedMs)}`}
          </p>
        </div>
        {live.length > 0 && (
          <ul className="flex flex-col gap-1.5">
            {live.map((session) => {
              const health = stream.health[session.id];
              return (
                <li key={session.id} className="flex min-w-0 items-center gap-2 text-[12.5px]">
                  <span className="shrink-0 font-semibold">{session.agent ?? "agent"}</span>
                  <span className={sessionChipClass(session.status)}>{session.status}</span>
                  {typeof health?.steps === "number" && (
                    <span className="shrink-0 font-mono text-[11px] text-ink-soft">Step {health.steps}</span>
                  )}
                  {session.task && (
                    <span className="line-clamp-1 min-w-0 flex-1 text-ink-faint">{session.task}</span>
                  )}
                  {session.agent_view_url && (
                    <a
                      className="ml-auto shrink-0 font-semibold whitespace-nowrap text-brand hover:underline"
                      href={session.agent_view_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Watch ↗
                    </a>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

// H emits roughly one observation per 10-20s agent step; 4s keeps tiles fresh
// without hammering the frame endpoint (which itself caches just under this).
const FRAME_MS = 4_000;

// Long enough to read a "✓ dismissed cookie wall" flash; just over one frame poll.
const FLASH_MS = 4_500;

// Status pill floated over a tile's screenshot. Dark shell on purpose: the light
// .chip classes vanish against arbitrary page screenshots.
const TILE_PILL_CLASS =
  "absolute top-2 left-2 z-10 inline-flex items-center gap-1.5 rounded-full bg-black/65 px-2 py-0.5 text-[10.5px] font-semibold text-white backdrop-blur";

/** "https://www.eventbrite.com/x" -> "eventbrite.com"; null when unparsable. */
function hostnameOf(url?: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "") || null;
  } catch {
    return null;
  }
}

/** Live screenshot tiles of every progressing browser session; hidden when idle. */
function LiveBrowserGrid({ eventId, stream }: { eventId: string; stream: AgentStreamState }) {
  const live = stream.report?.succeeded
    ? stream.report.sessions.filter((session) => isProgressing(session.status))
    : [];
  const [frames, setFrames] = useState<Record<string, SessionFrame>>({});
  const inFlight = useRef(false);
  // Poll on membership changes, not on the report object identity (a new report
  // arrives every 5s and would otherwise reset the frame interval each tick).
  const ids = live.map((session) => session.id).join(",");

  useEffect(() => {
    if (!ids) return;
    let cancelled = false;
    const sessionIds = ids.split(",");

    const tick = async () => {
      if (inFlight.current) return; // frames are ~57KB each; never stack polls
      inFlight.current = true;
      try {
        const checks = await Promise.all(
          sessionIds.map((id) => getSessionFrame(eventId, id).catch(() => null)),
        );
        if (cancelled) return;
        // Keep only current tiles, and each tile's last good frame — a failed
        // check (or a session still without a screenshot) never blanks a tile.
        setFrames((previous) => {
          const merged: Record<string, SessionFrame> = {};
          for (const id of sessionIds) {
            if (previous[id]) merged[id] = previous[id];
          }
          for (const check of checks) {
            if (check?.succeeded && check.image_base64) merged[check.session_id] = check;
          }
          return merged;
        });
      } finally {
        inFlight.current = false;
      }
    };

    void tick();
    const poller = setInterval(() => void tick(), FRAME_MS);
    return () => {
      cancelled = true;
      clearInterval(poller);
    };
  }, [eventId, ids]);

  if (live.length === 0) return null;
  return (
    <section
      aria-label="Live browser sessions"
      className="sticky top-16 z-10 -mx-6 border-b border-line bg-canvas/95 px-6 pt-3 pb-3 backdrop-blur"
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className="eyebrow">Live browsers</h3>
        <span className="inline-flex items-center gap-1.5 font-mono text-[10.5px] font-bold tracking-[0.12em] text-positive-deep uppercase">
          <span className="dot dot-green animate-pulse" aria-hidden="true" />
          Live
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {live.map((session, index) => (
          <LiveTile
            key={session.id}
            session={session}
            frame={frames[session.id]}
            steps={stream.health[session.id]?.steps}
            // A lone browser gets the full column; with three or more, the first
            // (report order — stable, no reshuffling mid-run) leads as a hero tile.
            featured={live.length === 1 || (live.length >= 3 && index === 0)}
          />
        ))}
      </div>
    </section>
  );
}

/** One browser's live view: the newest screenshot, crossfaded over the previous one. */
function LiveTile({
  session,
  frame,
  steps,
  featured = false,
}: {
  session: AgentSessionSummary;
  frame?: SessionFrame;
  steps?: number | null;
  featured?: boolean;
}) {
  // Double buffer: the previous frame stays underneath while the new one fades in.
  const [shots, setShots] = useState<{ under?: string; over?: string; overKey?: string }>({});
  useEffect(() => {
    if (!frame?.image_base64) return;
    const src = `data:${frame.media_type ?? "image/png"};base64,${frame.image_base64}`;
    setShots((previous) =>
      previous.over === src
        ? previous
        : { under: previous.over, over: src, overKey: frame.at ?? src.slice(-32) },
    );
  }, [frame]);

  // Flash the newest "✓ cleared" label whenever the session's cleared list grows.
  // The timer lives in a ref so the every-4s frame polls can't cancel it early.
  const [flash, setFlash] = useState<string | null>(null);
  const seenCleared = useRef(0);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const cleared = frame?.obstacles_cleared ?? [];
    if (cleared.length <= seenCleared.current) return;
    seenCleared.current = cleared.length;
    setFlash(cleared[cleared.length - 1]);
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(null), FLASH_MS);
  }, [frame]);
  useEffect(() => {
    return () => {
      if (flashTimer.current) clearTimeout(flashTimer.current);
    };
  }, []);

  const agent = session.agent ?? "agent";
  const host = hostnameOf(frame?.page_url);
  return (
    <figure
      className={`relative overflow-hidden rounded-[10px] border border-line bg-surface shadow-card ${
        // 16:9 (not 16:10) on the hero keeps the sticky grid under ~460px of the column.
        featured ? "col-span-full aspect-[16/9]" : "aspect-[16/10]"
      }`}
    >
      {shots.under && (
        <img src={shots.under} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover" />
      )}
      {shots.over ? (
        <img
          key={shots.overKey}
          src={shots.over}
          alt={`Live browser — ${agent}`}
          className="absolute inset-0 h-full w-full object-cover transition-opacity duration-500 starting:opacity-0"
        />
      ) : (
        <div className="absolute inset-0 grid animate-pulse place-items-center text-[12px] text-ink-faint">
          Starting browser…
        </div>
      )}
      {frame?.handling ? (
        <span className={TILE_PILL_CLASS}>
          <span className="dot dot-amber animate-pulse" aria-hidden="true" />
          {frame.handling === "recovering" ? "recovering…" : `handling: ${frame.handling}`}
        </span>
      ) : flash ? (
        <span className={TILE_PILL_CLASS}>
          <span className="dot dot-green" aria-hidden="true" />✓ {flash}
        </span>
      ) : null}
      <figcaption className="absolute inset-x-0 bottom-0 flex items-center gap-2 bg-gradient-to-t from-black/60 to-transparent px-2.5 pt-6 pb-1.5 text-white">
        <span className="shrink-0 text-[11.5px] font-semibold">{agent}</span>
        {typeof steps === "number" && (
          <span className="shrink-0 font-mono text-[10px] opacity-80">Step {steps}</span>
        )}
        {frame?.page_title && (
          <span className="line-clamp-1 min-w-0 flex-1 text-[10.5px] opacity-80">{frame.page_title}</span>
        )}
        {host && <span className="ml-auto shrink-0 font-mono text-[10px] opacity-80">{host}</span>}
      </figcaption>
    </figure>
  );
}

function quietLine(elapsedMs: number, intake: boolean): string {
  if (intake) return `Thinking… ${formatElapsed(elapsedMs)} — structuring your event brief.`;
  if (elapsedMs < 8_000) return "Working on it — routing to the right agent…";
  return `Thinking… ${formatElapsed(elapsedMs)} — this step runs without a browser; reasoning can take a minute.`;
}

function formatElapsed(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function AssistantAvatar() {
  return (
    <span className="relative mt-1 size-6 shrink-0 rounded-[7px] bg-brand" aria-hidden="true">
      <span className="absolute inset-[7px] rounded-full border-2 border-white" />
    </span>
  );
}

function outcomeChipClass(outcome: string): string {
  if (outcome === "success") return "chip chip-green";
  if (outcome === "partial") return "chip chip-amber";
  return "chip chip-red"; // infeasible | blocked
}

function sessionChipClass(status: string): string {
  if (status === "running") return "chip chip-green";
  if (status === "queued" || status === "pending" || status === "starting") return "chip chip-amber";
  if (status === "failed" || status === "timed_out" || status === "error") return "chip chip-red";
  return "chip chip-gray"; // paused | idle | awaiting_tool_results | completed
}
