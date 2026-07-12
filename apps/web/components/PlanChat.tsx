"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { awaitRun, sendChatMessage } from "@/lib/api";
import type { AgentRunRecord, PlanChatMessage } from "@/types";

interface PlanChatProps {
  eventId: string;
}

const SUGGESTIONS = [
  "Find three caterers near Pier 27 in San Francisco that can serve 320 guests on Aug 6",
  "Compare DJs available on Aug 6 under $3,500 with strong reviews",
  "Research custom tote bag suppliers that can deliver 350 units by Aug 4",
];

/** One continuous planning chat: each prompt runs as a real agent task and the
 * result lands back in the thread. History persists locally per event. */
export function PlanChat({ eventId }: PlanChatProps) {
  const storageKey = `occasion:plan-chat:${eventId}`;
  const pendingKey = `occasion:plan-chat-pending:${eventId}`;
  const [messages, setMessages] = useState<PlanChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [clearArmed, setClearArmed] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const threadEndRef = useRef<HTMLDivElement>(null);

  // Restore the conversation once on mount; only persist after that restore.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(storageKey);
      if (stored) setMessages(JSON.parse(stored) as PlanChatMessage[]);
    } catch {
      // Corrupt or unavailable storage just means starting fresh.
    }
    setHydrated(true);
  }, [storageKey]);

  // A turn interrupted by a reload keeps running server-side; pick its poll back up.
  useEffect(() => {
    const pendingRunId = window.localStorage.getItem(pendingKey);
    if (!pendingRunId) return;
    setPending(true);
    awaitRun(pendingRunId)
      .then((run) => setMessages((prev) => [...prev, resultMessage(run)]))
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error);
        setMessages((prev) => [...prev, { ...newMessage("assistant", message), isError: true }]);
      })
      .finally(() => {
        window.localStorage.removeItem(pendingKey);
        setPending(false);
      });
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

  async function send(text: string) {
    const prompt = text.trim();
    if (!prompt || pending) return;
    setDraft("");
    setClearArmed(false);
    setMessages((prev) => [...prev, newMessage("user", prompt)]);
    setPending(true);
    try {
      const started = await sendChatMessage(prompt, eventId);
      // Remember the in-flight run so a reload resumes the poll instead of losing it.
      window.localStorage.setItem(pendingKey, started.id);
      const settled = await awaitRun(started.id);
      setMessages((prev) => [...prev, resultMessage(settled)]);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setMessages((prev) => [...prev, { ...newMessage("assistant", message), isError: true }]);
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

  const showEmptyState = hydrated && messages.length === 0 && !pending;

  return (
    <main className="mx-auto flex w-full max-w-[860px] flex-1 flex-col px-6">
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
            <div className="flex flex-col gap-4 pt-4 pb-2">
              {messages.map((message) =>
                message.role === "user" ? (
                  <UserBubble key={message.id} message={message} />
                ) : (
                  <AssistantBubble key={message.id} message={message} />
                ),
              )}
              {pending && <PendingBubble />}
              <div ref={threadEndRef} />
            </div>
          </>
        )}
      </div>

      <div className="sticky bottom-0 bg-canvas pt-2 pb-5">
        <form
          onSubmit={handleSubmit}
          className="card flex items-end gap-2 rounded-2xl p-2 focus-within:border-brand"
        >
          <label className="sr-only" htmlFor="plan-chat-input">
            Message Occasion
          </label>
          <textarea
            id="plan-chat-input"
            ref={composerRef}
            rows={1}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            placeholder="Ask Occasion to research, compare, or plan…"
            className="max-h-40 min-h-[40px] w-full flex-1 resize-none bg-transparent px-2.5 py-2 text-[13.5px] leading-normal outline-none [field-sizing:content] placeholder:text-ink-faint"
          />
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

function newMessage(role: PlanChatMessage["role"], content: string): PlanChatMessage {
  return { id: crypto.randomUUID(), role, content, createdAt: new Date().toISOString() };
}

function resultMessage(run: AgentRunRecord): PlanChatMessage {
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

function UserBubble({ message }: { message: PlanChatMessage }) {
  return (
    <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-[6px] bg-brand px-4 py-2.5 text-[13.5px] leading-relaxed break-words whitespace-pre-wrap text-white">
      {message.content}
    </div>
  );
}

function AssistantBubble({ message }: { message: PlanChatMessage }) {
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

function PendingBubble() {
  return (
    <div className="flex gap-2.5" role="status">
      <AssistantAvatar />
      <div className="flex min-w-0 max-w-[92%] items-center gap-3 rounded-2xl rounded-bl-[6px] border border-brand-mist bg-brand-soft px-4 py-3">
        <span
          className="size-4 shrink-0 animate-spin rounded-full border-2 border-brand-mist border-t-brand"
          aria-hidden="true"
        />
        <p className="text-[13px] leading-relaxed text-ink-soft">
          Working on it — routing to the right agent; browser tasks can take a few minutes. Keep
          this page open.
        </p>
      </div>
    </div>
  );
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
