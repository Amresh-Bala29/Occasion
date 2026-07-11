import { TalkToOccasion } from "@/components/TalkToOccasion";

interface TopbarProps {
  section: string;
  eventName: string;
  agentsWorking: number;
}

/** Shared header bar: breadcrumb, live agents pill, and the Talk to Occasion entry point. */
export function Topbar({ section, eventName, agentsWorking }: TopbarProps) {
  // Fixed md+ height so full-height pages can size against it (h-[calc(100vh-64px)]).
  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3.5 border-b border-line bg-surface px-6 py-[13px] md:h-16 md:py-0">
      <div className="flex min-w-0 items-baseline gap-2">
        <span className="text-[15.5px] font-bold">{section}</span>
        <span className="text-ink-faint" aria-hidden="true">
          /
        </span>
        <span className="truncate text-[13.5px] text-ink-soft">{eventName}</span>
      </div>
      <div className="flex items-center gap-2.5">
        <span className="inline-flex items-center gap-2 rounded-full border border-line-strong bg-surface px-3.5 py-[7px] text-[13px] font-medium whitespace-nowrap">
          <span className="dot dot-green" aria-hidden="true" />
          {agentsWorking} agents working
        </span>
        <TalkToOccasion />
      </div>
    </header>
  );
}
