"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import type { Conversation, InboxFilter, InboxMessage } from "@/types";

interface MessagesInboxProps {
  initialConversations: Conversation[];
  /** Conversation to open on load, from /dashboard/messages?thread=<id>. */
  initialThreadId?: string;
}

const FILTERS: { key: InboxFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
  { key: "archived", label: "Archived" },
];

const EMPTY_LIST_COPY: Record<InboxFilter, string> = {
  all: "No conversations yet.",
  unread: "You're all caught up — no unread messages.",
  archived: "No archived conversations.",
};

/** Unified inbox: every vendor thread from every channel in one place.
 * Reads and local replies mutate client state only until the messages API lands. */
export function MessagesInbox({ initialConversations, initialThreadId }: MessagesInboxProps) {
  // A deep-linked thread wins the initial selection; if it's archived, start on
  // the Archived filter so its row is visible in the list.
  const linkedThread = initialThreadId
    ? initialConversations.find((c) => c.id === initialThreadId)
    : undefined;

  const [conversations, setConversations] = useState(initialConversations);
  const [filter, setFilter] = useState<InboxFilter>(linkedThread?.archived ? "archived" : "all");
  const [selectedId, setSelectedId] = useState(
    () => linkedThread?.id ?? initialConversations.find((c) => !c.archived)?.id ?? null,
  );
  const [mobileThreadOpen, setMobileThreadOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const selected = conversations.find((c) => c.id === selectedId) ?? null;

  const visible = conversations.filter((c) => {
    if (filter === "archived") return c.archived;
    if (filter === "unread") return !c.archived && c.unread;
    return !c.archived;
  });

  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [selectedId, selected?.messages.length]);

  // A displayed thread counts as read, including the one selected on load.
  useEffect(() => {
    if (!selectedId) return;
    setConversations((prev) =>
      prev.map((c) => (c.id === selectedId && c.unread ? { ...c, unread: false } : c)),
    );
  }, [selectedId]);

  useEffect(() => {
    if (!menuOpen) return;
    function handlePointerDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    }
    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  function openConversation(id: string) {
    setSelectedId(id);
    setMobileThreadOpen(true);
    setDraft("");
  }

  function toggleArchived() {
    if (!selected) return;
    setConversations((prev) =>
      prev.map((c) => (c.id === selected.id ? { ...c, archived: !c.archived } : c)),
    );
    setMenuOpen(false);
  }

  function markAsUnread() {
    if (!selected) return;
    setConversations((prev) =>
      prev.map((c) => (c.id === selected.id ? { ...c, unread: true } : c)),
    );
    // Deselect, or the read-marking effect would clear the flag right away.
    setSelectedId(null);
    setMobileThreadOpen(false);
    setMenuOpen(false);
  }

  function sendMessage() {
    const text = draft.trim();
    if (!text || !selected) return;
    const message: InboxMessage = {
      id: crypto.randomUUID(),
      author: "You",
      fromMe: true,
      day: "Today",
      time: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
      body: text,
    };
    setConversations((prev) =>
      prev.map((c) =>
        c.id === selected.id
          ? { ...c, messages: [...c.messages, message], preview: text, timeLabel: "Now" }
          : c,
      ),
    );
    setDraft("");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendMessage();
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  function pickQuickReply(reply: string) {
    setDraft(reply);
    composerRef.current?.focus();
  }

  return (
    <div className="flex min-h-0 flex-1 bg-surface md:h-[calc(100vh-64px)] md:overflow-hidden">
      {/* Conversation list */}
      <div
        className={`${mobileThreadOpen ? "hidden md:flex" : "flex"} w-full shrink-0 flex-col border-r border-line md:w-[340px] xl:w-[360px]`}
      >
        <div className="flex gap-1 border-b border-line px-3 pt-2" role="tablist" aria-label="Inbox filters">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              role="tab"
              aria-selected={filter === f.key}
              onClick={() => setFilter(f.key)}
              className={`cursor-pointer rounded-t-md px-3 py-2 text-[13px] ${
                filter === f.key
                  ? "-mb-px border-b-2 border-brand font-semibold text-brand-deep"
                  : "font-medium text-ink-soft hover:text-ink"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto">
          {visible.length === 0 ? (
            <p className="px-6 py-10 text-center text-[13px] text-ink-faint">{EMPTY_LIST_COPY[filter]}</p>
          ) : (
            visible.map((conversation) => (
              <ConversationRow
                key={conversation.id}
                conversation={conversation}
                selected={conversation.id === selectedId}
                onOpen={() => openConversation(conversation.id)}
              />
            ))
          )}
        </div>
      </div>

      {/* Thread */}
      <div className={`${mobileThreadOpen ? "flex" : "hidden md:flex"} min-w-0 flex-1 flex-col`}>
        {selected ? (
          <>
            <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
              <div className="flex min-w-0 items-center gap-2">
                <button
                  type="button"
                  className="-ml-1 cursor-pointer rounded-md p-1 text-ink-soft hover:text-ink md:hidden"
                  aria-label="Back to inbox"
                  onClick={() => setMobileThreadOpen(false)}
                >
                  ←
                </button>
                <div className="min-w-0">
                  <h2 className="truncate text-[15px] font-bold">{selected.name}</h2>
                  <div className="mt-0.5 flex items-center gap-2">
                    <span className="truncate text-[12.5px] text-ink-soft">{selected.subtitle}</span>
                    <span className="chip chip-gray">{selected.channel}</span>
                  </div>
                </div>
              </div>
              {/* Wrapper carries menuRef so a click on the toggle isn't treated as outside. */}
              <div ref={menuRef} className="relative">
                <button
                  type="button"
                  className="cursor-pointer rounded-md px-2 py-1 text-[18px] leading-none text-ink-faint hover:text-ink"
                  aria-label="Conversation actions"
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen((open) => !open)}
                >
                  …
                </button>
                {menuOpen && (
                  <div
                    role="menu"
                    className="card absolute top-full right-0 z-10 mt-1 w-44 py-1 shadow-modal"
                  >
                    <button
                      type="button"
                      role="menuitem"
                      className="w-full cursor-pointer px-3.5 py-2 text-left text-[13px] hover:bg-[#f4f6fb]"
                      onClick={toggleArchived}
                    >
                      {selected.archived ? "Unarchive" : "Archive"}
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      className="w-full cursor-pointer px-3.5 py-2 text-left text-[13px] hover:bg-[#f4f6fb]"
                      onClick={markAsUnread}
                    >
                      Mark as unread
                    </button>
                  </div>
                )}
              </div>
            </div>

            <div ref={threadRef} className="flex-1 overflow-y-auto px-6 py-5">
              <ThreadMessages messages={selected.messages} avatarInitials={selected.avatarInitials} />
            </div>

            <div className="sticky bottom-0 border-t border-line bg-surface px-4 pt-3 pb-4">
              {selected.quickReplies.length > 0 && (
                <div className="mb-3 flex flex-wrap justify-center gap-2">
                  {selected.quickReplies.map((reply) => (
                    <button
                      key={reply}
                      type="button"
                      className="btn btn-secondary rounded-lg text-[12.5px]"
                      onClick={() => pickQuickReply(reply)}
                    >
                      {reply}
                    </button>
                  ))}
                </div>
              )}
              <form
                onSubmit={handleSubmit}
                className="rounded-xl border border-line-strong bg-surface focus-within:border-brand focus-within:shadow-[0_0_0_3px_var(--color-brand-soft)]"
              >
                <label className="sr-only" htmlFor="inbox-composer">
                  Type a message
                </label>
                <textarea
                  id="inbox-composer"
                  ref={composerRef}
                  rows={1}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={handleComposerKeyDown}
                  placeholder="Type a message"
                  className="max-h-40 min-h-[44px] w-full resize-none bg-transparent px-3.5 pt-3 pb-1 text-[13.5px] leading-normal outline-none [field-sizing:content] placeholder:text-ink-faint"
                />
                <div className="flex items-center gap-1 px-2.5 pb-2">
                  <button
                    type="button"
                    className="cursor-default rounded-md px-2 py-1 text-[13px] font-semibold text-ink-faint"
                    title="Formatting — coming soon"
                    aria-hidden="true"
                    tabIndex={-1}
                  >
                    Aa
                  </button>
                  <button
                    type="button"
                    className="cursor-default rounded-md px-2 py-1 text-ink-faint"
                    title="Attach link — coming soon"
                    aria-hidden="true"
                    tabIndex={-1}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path
                        d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.5 1.5M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7L12 19"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                    </svg>
                  </button>
                  <span className="flex-1" />
                  <button type="submit" className="btn btn-primary" disabled={!draft.trim()}>
                    Send
                  </button>
                </div>
              </form>
            </div>
          </>
        ) : (
          <p className="m-auto px-6 text-[13px] text-ink-faint">Select a conversation to read it.</p>
        )}
      </div>
    </div>
  );
}

interface ConversationRowProps {
  conversation: Conversation;
  selected: boolean;
  onOpen: () => void;
}

function ConversationRow({ conversation, selected, onOpen }: ConversationRowProps) {
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
          <span className={`truncate text-[14px] ${conversation.unread ? "font-bold" : "font-semibold"}`}>
            {conversation.name}
          </span>
          <span className="flex shrink-0 items-center gap-1.5">
            {conversation.unread && <span className="dot dot-blue size-[7px]" aria-label="Unread" />}
            <span className="text-[11.5px] text-ink-faint">{conversation.timeLabel}</span>
          </span>
        </span>
        <span className="mt-0.5 block truncate text-[12.5px] text-ink-soft">{conversation.subtitle}</span>
        <span
          className={`mt-1 block truncate text-[12.5px] ${
            conversation.unread ? "font-medium text-ink" : "text-ink-faint"
          }`}
        >
          {conversation.preview}
        </span>
      </span>
    </button>
  );
}

interface ThreadMessagesProps {
  messages: InboxMessage[];
  avatarInitials: string;
}

function ThreadMessages({ messages, avatarInitials }: ThreadMessagesProps) {
  let lastDay: string | null = null;

  return (
    <div className="flex flex-col gap-5">
      {messages.map((message) => {
        const showDay = message.day !== lastDay;
        lastDay = message.day;
        return (
          <div key={message.id}>
            {showDay && <p className="pb-4 text-center text-[11.5px] text-ink-faint">{message.day}</p>}
            <div className="flex gap-3">
              <span
                className={`flex size-8 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                  message.fromMe ? "bg-brand-soft text-brand-deep" : "bg-[#e3e8f2] text-ink-soft"
                }`}
                aria-hidden="true"
              >
                {message.fromMe ? "AB" : avatarInitials}
              </span>
              <div className="min-w-0">
                <div className="flex items-baseline gap-2">
                  <span className="text-[13.5px] font-semibold">{message.author}</span>
                  <span className="text-[11px] text-ink-faint">{message.time}</span>
                </div>
                <p className="mt-1 text-[13.5px] leading-[1.6] break-words whitespace-pre-line text-ink">
                  {message.body}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
