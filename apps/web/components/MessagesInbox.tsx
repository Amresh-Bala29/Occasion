"use client";

import { useEffect, useRef, useState } from "react";

import type { Conversation } from "@/types";

interface MessagesInboxProps {
  initialConversations: Conversation[];
  /** Conversation to open on load, from /dashboard/messages?thread=<id>. */
  initialThreadId?: string;
}

/** Where a planned email is in its send lifecycle, tracked in the browser only. */
type SendState = "planned" | "sending" | "sent";

/** How long the liftoff animation runs before the email flips to Sent. */
const SEND_ANIMATION_MS = 1100;

/** Outbox of planned vendor emails: each is a single outgoing draft Occasion
 * prepared, ready to send. "Sending" is a local, session-only animation —
 * nothing leaves the browser and a reload restores every email to Planned. */
export function MessagesInbox({ initialConversations, initialThreadId }: MessagesInboxProps) {
  const linkedThread = initialThreadId
    ? initialConversations.find((c) => c.id === initialThreadId)
    : undefined;

  const [selectedId, setSelectedId] = useState(
    () => linkedThread?.id ?? initialConversations[0]?.id ?? null,
  );
  const [mobileThreadOpen, setMobileThreadOpen] = useState(Boolean(linkedThread));
  const [sentIds, setSentIds] = useState<Set<string>>(() => new Set());
  const [sendingId, setSendingId] = useState<string | null>(null);
  const sendTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  const selected = initialConversations.find((c) => c.id === selectedId) ?? null;
  const plannedCount = initialConversations.filter((c) => !sentIds.has(c.id)).length;

  // Scroll a freshly opened email to the top so its subject leads.
  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = 0;
  }, [selectedId]);

  // Cancel a pending send if the inbox unmounts mid-animation.
  useEffect(() => () => {
    if (sendTimer.current) clearTimeout(sendTimer.current);
  }, []);

  function sendStateOf(id: string): SendState {
    if (sentIds.has(id)) return "sent";
    if (sendingId === id) return "sending";
    return "planned";
  }

  function openConversation(id: string) {
    setSelectedId(id);
    setMobileThreadOpen(true);
  }

  function sendEmail(id: string) {
    // One send animates at a time; a sent email can't be re-sent.
    if (sendingId || sentIds.has(id)) return;
    setSendingId(id);
    sendTimer.current = setTimeout(() => {
      setSentIds((prev) => new Set(prev).add(id));
      setSendingId(null);
      sendTimer.current = null;
    }, SEND_ANIMATION_MS);
  }

  return (
    <div className="flex min-h-0 flex-1 bg-surface md:h-[calc(100vh-64px)] md:overflow-hidden">
      {/* Planned-email list */}
      <div
        className={`${mobileThreadOpen ? "hidden md:flex" : "flex"} w-full shrink-0 flex-col border-r border-line md:w-[340px] xl:w-[360px]`}
      >
        <div className="border-b border-line px-4 py-3">
          <h2 className="text-[14px] font-bold">Planned emails</h2>
          <p className="mt-0.5 text-[12.5px] text-ink-faint">
            {plannedCount === 0
              ? "All sent — nothing left in the outbox."
              : `${plannedCount} drafted by Occasion, ready to send.`}
          </p>
        </div>

        <div className="flex-1 overflow-y-auto">
          {initialConversations.length === 0 ? (
            <p className="px-6 py-10 text-center text-[13px] text-ink-faint">No planned emails yet.</p>
          ) : (
            initialConversations.map((conversation) => (
              <ConversationRow
                key={conversation.id}
                conversation={conversation}
                state={sendStateOf(conversation.id)}
                selected={conversation.id === selectedId}
                onOpen={() => openConversation(conversation.id)}
              />
            ))
          )}
        </div>
      </div>

      {/* Email */}
      <div className={`${mobileThreadOpen ? "flex" : "hidden md:flex"} min-w-0 flex-1 flex-col`}>
        {selected ? (
          <EmailView
            conversation={selected}
            state={sendStateOf(selected.id)}
            onBack={() => setMobileThreadOpen(false)}
            onSend={() => sendEmail(selected.id)}
            scrollRef={threadRef}
          />
        ) : (
          <p className="m-auto px-6 text-[13px] text-ink-faint">Select an email to read it.</p>
        )}
      </div>
    </div>
  );
}

interface StatusChipProps {
  state: SendState;
}

function StatusChip({ state }: StatusChipProps) {
  if (state === "sent") return <span className="chip chip-green">Sent</span>;
  if (state === "sending") return <span className="chip chip-amber">Sending</span>;
  return <span className="chip chip-blue">Planned</span>;
}

interface ConversationRowProps {
  conversation: Conversation;
  state: SendState;
  selected: boolean;
  onOpen: () => void;
}

function ConversationRow({ conversation, state, selected, onOpen }: ConversationRowProps) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`relative flex w-full cursor-pointer gap-3 border-b border-line px-4 py-3.5 text-left hover:bg-[#f7f9fc] ${
        selected ? "bg-brand-soft/60" : ""
      }`}
    >
      {selected && <span className="absolute inset-y-0 left-0 w-[3px] bg-brand" aria-hidden="true" />}
      <span
        className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[#e3e8f2] text-[12px] font-semibold text-ink-soft"
        aria-hidden="true"
      >
        {conversation.avatarInitials}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="truncate text-[14px] font-semibold">{conversation.name}</span>
          <StatusChip state={state} />
        </span>
        <span className="mt-0.5 block truncate text-[12.5px] text-ink-soft">{conversation.subtitle}</span>
        <span className="mt-1 flex items-baseline justify-between gap-2">
          <span
            className={`truncate text-[12.5px] ${state === "sent" ? "text-ink-faint" : "font-medium text-ink"}`}
          >
            {conversation.preview}
          </span>
          <span className="shrink-0 text-[11.5px] text-ink-faint">{conversation.timeLabel}</span>
        </span>
      </span>
    </button>
  );
}

interface EmailViewProps {
  conversation: Conversation;
  state: SendState;
  onBack: () => void;
  onSend: () => void;
  scrollRef: React.RefObject<HTMLDivElement | null>;
}

function EmailView({ conversation, state, onBack, onSend, scrollRef }: EmailViewProps) {
  const email = conversation.messages[0];

  return (
    <>
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            className="-ml-1 cursor-pointer rounded-md p-1 text-ink-soft hover:text-ink md:hidden"
            aria-label="Back to outbox"
            onClick={onBack}
          >
            ←
          </button>
          <div className="min-w-0">
            <h2 className="truncate text-[15px] font-bold">{conversation.name}</h2>
            <div className="mt-0.5 flex items-center gap-2">
              <span className="truncate text-[12.5px] text-ink-soft">{conversation.subtitle}</span>
              <span className="chip chip-gray">{conversation.channel}</span>
            </div>
          </div>
        </div>
        <StatusChip state={state} />
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto max-w-2xl">
          <p className="text-[11px] font-semibold tracking-[0.02em] text-ink-faint uppercase">Subject</p>
          <h3 className="mt-1 text-[17px] leading-snug font-bold">{conversation.preview}</h3>
          <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line pb-4 text-[12.5px]">
            <span className="text-ink-faint">To</span>
            <span className="font-medium text-ink">{conversation.name}</span>
            <span className="text-ink-faint">· {conversation.subtitle}</span>
          </div>
          {email && (
            <p className="mt-4 text-[14px] leading-[1.7] break-words whitespace-pre-line text-ink">
              {email.body}
            </p>
          )}
        </div>
      </div>

      <SendBar state={state} onSend={onSend} />
    </>
  );
}

interface SendBarProps {
  state: SendState;
  onSend: () => void;
}

function SendBar({ state, onSend }: SendBarProps) {
  return (
    <div className="sticky bottom-0 flex min-h-[68px] items-center justify-between gap-3 border-t border-line bg-surface px-5 py-3">
      {state === "sent" ? (
        <div
          className="animate-sent-pop flex items-center gap-2 text-positive-deep"
          role="status"
          aria-live="polite"
        >
          <CheckIcon />
          <span className="text-[13.5px] font-semibold">Sent</span>
          <span className="text-[12.5px] text-ink-faint">· just now</span>
        </div>
      ) : (
        <>
          <p className="text-[12.5px] text-ink-faint">
            {state === "sending" ? "Delivering your email…" : "Drafted by Occasion · review, then send"}
          </p>
          <div className="relative">
            <button
              type="button"
              className="btn btn-primary flex items-center gap-2"
              onClick={onSend}
              disabled={state === "sending"}
            >
              {state === "sending" ? (
                <>
                  <span
                    className="size-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white"
                    aria-hidden="true"
                  />
                  Sending…
                </>
              ) : (
                <>
                  <PlaneIcon />
                  Send
                </>
              )}
            </button>
            {state === "sending" && (
              <PlaneIcon className="animate-send-liftoff pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-brand" />
            )}
          </div>
        </>
      )}
    </div>
  );
}

function PlaneIcon({ className }: { className?: string }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M20 6 9 17l-5-5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
