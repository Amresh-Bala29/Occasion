"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useEvent } from "@/hooks/useEvent";

interface SidebarProps {
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

export function Sidebar({ messagesCount }: SidebarProps) {
  const pathname = usePathname();
  const { autoApproveLimit } = useEvent();

  const navEntries: NavEntry[] = [
    { label: "Ask Occasion", href: "/dashboard/ask" },
    { label: "Overview", href: "/dashboard" },
    { label: "Plan", href: "/dashboard/plan" },
    { label: "Vendors", href: "/dashboard/vendors" },
    { label: "Budget", href: "/dashboard/budget" },
    { label: "Calendar", href: "/dashboard/calendar" },
    { label: "Messages", href: "/dashboard/messages", badge: messagesCount, badgeTone: "gray" },
    { label: "Settings", href: "/dashboard/approvals" },
  ];

  return (
    <aside className="flex flex-col gap-4 border-b border-line bg-surface px-3.5 py-[18px] md:sticky md:top-0 md:h-screen md:overflow-y-auto md:border-r md:border-b-0">
      <div className="flex items-center gap-2.5 px-1.5 pt-0.5">
        <span className="relative size-[30px] shrink-0 rounded-[9px] bg-brand" aria-hidden="true">
          <span className="absolute inset-[9px] rounded-full border-[2.5px] border-white" />
        </span>
        <span className="text-[16.5px] font-bold tracking-[-0.01em]">Occasion</span>
      </div>

      <ProjectShortcuts />

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

/** Workspace shortcuts that replaced the per-event switcher; projects are browsed
 *  on /projects and picking one there sets the active-event cookie. */
function ProjectShortcuts() {
  return (
    <nav
      aria-label="Projects"
      className="divide-y divide-line overflow-hidden rounded-[10px] border border-line-strong"
    >
      <ShortcutRow href="/projects" label="All Projects" icon={GRID_ICON} />
      <ShortcutRow href="/ask?new=1" label="New Project" icon={PLUS_ICON} accent />
      <ShortcutRow href="/dashboard/approvals" label="Project Settings" icon={SLIDERS_ICON} />
    </nav>
  );
}

function ShortcutRow({
  href,
  label,
  icon,
  accent = false,
}: {
  href: string;
  label: string;
  icon: React.ReactNode;
  accent?: boolean;
}) {
  const tone = accent ? "text-brand hover:bg-brand-soft" : "text-ink hover:bg-[#f4f6fb]";

  return (
    <Link href={href} className={`flex items-center gap-2.5 px-3 py-[9px] text-[13px] font-semibold ${tone}`}>
      <span className={accent ? "text-brand" : "text-ink-faint"} aria-hidden="true">
        {icon}
      </span>
      {label}
    </Link>
  );
}

const GRID_ICON = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <rect x="1.5" y="1.5" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.5" />
    <rect x="7.9" y="1.5" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.5" />
    <rect x="1.5" y="7.9" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.5" />
    <rect x="7.9" y="7.9" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

const PLUS_ICON = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M7 2.2v9.6M2.2 7h9.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
  </svg>
);

const SLIDERS_ICON = (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M1.5 4.2h11M1.5 9.8h11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="8.8" cy="4.2" r="1.9" fill="#fff" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="5.2" cy="9.8" r="1.9" fill="#fff" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

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
