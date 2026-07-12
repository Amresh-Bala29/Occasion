"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useEvent } from "@/hooks/useEvent";
import { EVENT_COOKIE } from "@/lib/api";
import type { EventOverview } from "@/types";

interface SidebarProps {
  activeEvent: string;
  activeEventId: string;
  events: EventOverview[];
  messagesCount: number;
}

interface NavEntry {
  label: string;
  href: string;
  badge?: number;
  badgeTone?: "gray" | "amber";
}

const BADGE_TONE_CLASSES = {
  gray: "bg-[#eceff5] text-ink-soft",
  amber: "bg-warn-soft text-warn-deep",
} as const;

export function Sidebar({ activeEvent, activeEventId, events, messagesCount }: SidebarProps) {
  const pathname = usePathname();
  const { approvals, autoApproveLimit } = useEvent();

  const navEntries: NavEntry[] = [
    { label: "Overview", href: "/dashboard" },
    { label: "Plan", href: "/dashboard/plan" },
    { label: "Vendors", href: "/dashboard/vendors" },
    { label: "Budget", href: "/dashboard/budget" },
    { label: "Calendar", href: "/dashboard/calendar" },
    { label: "Messages", href: "/dashboard/messages", badge: messagesCount, badgeTone: "gray" },
    { label: "Approvals", href: "/dashboard/approvals", badge: approvals.length, badgeTone: "amber" },
    { label: "Post-event", href: "/dashboard/post-event" },
  ];

  return (
    <aside className="flex flex-col gap-4 border-b border-line bg-surface px-3.5 py-[18px] md:sticky md:top-0 md:h-screen md:overflow-y-auto md:border-r md:border-b-0">
      <div className="flex items-center gap-2.5 px-1.5 pt-0.5">
        <span className="relative size-[30px] shrink-0 rounded-[9px] bg-brand" aria-hidden="true">
          <span className="absolute inset-[9px] rounded-full border-[2.5px] border-white" />
        </span>
        <span className="text-[16.5px] font-bold tracking-[-0.01em]">Occasion</span>
      </div>

      <EventSwitcher activeEvent={activeEvent} activeEventId={activeEventId} events={events} />

      <nav
        className="flex flex-row gap-1 overflow-x-auto pb-0.5 md:flex-1 md:flex-col md:gap-0.5 md:overflow-visible md:pb-0"
        aria-label="Event sections"
      >
        {navEntries.map((entry) => (
          <NavItem key={entry.label} entry={entry} active={pathname === entry.href} />
        ))}
      </nav>

      <div className="hidden flex-col gap-3.5 md:flex">
        <div className="rounded-xl border border-[#ccd9f9] bg-[#eef3ff] px-3.5 py-3">
          <div className="flex items-center gap-[7px] text-[12.5px] font-semibold">
            <span className="dot dot-green" aria-hidden="true" />
            Spending guardrail
          </div>
          <p className="mt-1.5 text-[12px] leading-[1.55] text-ink-soft">
            Auto-approving purchases under <strong className="text-ink">{autoApproveLimit}</strong>.
            Larger spends need your sign-off.
          </p>
          <Link
            href="/dashboard/approvals"
            className="mt-2 inline-block text-[12px] font-semibold text-brand hover:underline"
          >
            Adjust limits
          </Link>
        </div>

        <div className="flex items-center gap-2.5 border-t border-line px-1.5 pt-3 pb-0.5">
          <span
            className="flex size-[30px] shrink-0 items-center justify-center rounded-full bg-[#e3e8f2] text-[11px] font-semibold text-ink-soft"
            aria-hidden="true"
          >
            AB
          </span>
          <span>
            <span className="block text-[13px] font-semibold">Amresh B.</span>
            <span className="block text-[11px] text-ink-faint">Organizer</span>
          </span>
        </div>
      </div>
    </aside>
  );
}

/** Active-event selector: picking an event sets the cookie the server pages read. */
function EventSwitcher({
  activeEvent,
  activeEventId,
  events,
}: {
  activeEvent: string;
  activeEventId: string;
  events: EventOverview[];
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  function switchTo(eventId: string) {
    setOpen(false);
    if (eventId === activeEventId) return;
    // Not httpOnly on purpose: the client sets it, server components read it.
    document.cookie = `${EVENT_COOKIE}=${encodeURIComponent(eventId)}; path=/; max-age=31536000`;
    router.refresh();
  }

  useEffect(() => {
    if (!open) return;
    function closeOnOutsideClick(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setOpen(false);
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        className="block w-full cursor-pointer rounded-[10px] border border-line-strong bg-surface px-3 py-2.5 text-left hover:border-[#c3cbdd]"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className="block font-mono text-[9.5px] font-semibold tracking-[0.14em] text-ink-soft uppercase">
          Active event
        </span>
        <span className="mt-1 flex items-center justify-between gap-2 text-[14px] font-semibold">
          {activeEvent}
          <svg
            className={`shrink-0 text-ink-faint transition-transform ${open ? "rotate-180" : ""}`}
            width="10"
            height="6"
            viewBox="0 0 10 6"
            fill="none"
            aria-hidden="true"
          >
            <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute inset-x-0 top-full z-30 mt-1.5 overflow-hidden rounded-[10px] border border-line bg-surface shadow-modal"
        >
          {events.map((event) => (
            <button
              key={event.id}
              type="button"
              role="menuitemradio"
              aria-checked={event.id === activeEventId}
              className="flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2.5 text-left text-[13.5px] font-semibold hover:bg-brand-soft"
              onClick={() => switchTo(event.id)}
            >
              <span className="min-w-0">
                <span className="block truncate">{event.shortName}</span>
                <span className="block text-[11px] font-normal text-ink-faint">
                  {event.statusLabel} · {event.date}
                </span>
              </span>
              {event.id === activeEventId && (
                <span className="text-brand" aria-hidden="true">
                  ✓
                </span>
              )}
            </button>
          ))}
          <div className="border-t border-line px-3 py-2.5 text-[12px] text-ink-faint">
            New events arrive here once Occasion plans them.
          </div>
        </div>
      )}
    </div>
  );
}

function NavItem({ entry, active }: { entry: NavEntry; active: boolean }) {
  const baseClasses =
    "relative flex items-center gap-2.5 whitespace-nowrap rounded-lg py-[9px] pr-3 pl-3.5 text-[14px]";
  const stateClasses = active
    ? "bg-brand-soft font-semibold text-brand-deep"
    : "font-medium text-ink-soft hover:bg-[#f4f6fb] hover:text-ink";

  return (
    <Link href={entry.href} className={`${baseClasses} ${stateClasses}`}>
      {active && (
        <span
          className="absolute top-[7px] bottom-[7px] left-0 hidden w-[3px] rounded-[2px] bg-brand md:block"
          aria-hidden="true"
        />
      )}
      {entry.label}
      {entry.badge !== undefined && entry.badge > 0 && entry.badgeTone && (
        <span
          className={`ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold ${BADGE_TONE_CLASSES[entry.badgeTone]}`}
        >
          {entry.badge}
        </span>
      )}
    </Link>
  );
}
