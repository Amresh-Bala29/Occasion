"use client";

import { useEvent } from "@/hooks/useEvent";
import type { AgentStatus, Tone } from "@/types";

interface AgentPanelProps {
  agents: AgentStatus[];
}

const RING_BY_TONE: Record<Tone, string> = {
  green: "border-positive",
  blue: "border-brand",
  amber: "border-warn",
  gray: "border-ink-mist",
};

const FILL_BY_TONE: Record<Tone, string> = {
  green: "bg-positive",
  blue: "bg-brand",
  amber: "bg-warn",
  gray: "bg-ink-mist",
};

const NAME_BY_TONE: Record<Tone, string> = {
  green: "text-positive-deep",
  amber: "text-warn-deep",
  blue: "",
  gray: "",
};

/** Right-hand rail: live per-agent status plus the recent activity feed. */
export function AgentPanel({ agents }: AgentPanelProps) {
  const { activity } = useEvent();

  return (
    <aside
      className="border-t border-line bg-surface px-[22px] pt-5 pb-7 md:col-start-2 xl:sticky xl:top-0 xl:col-start-3 xl:row-start-1 xl:h-screen xl:overflow-y-auto xl:border-t-0 xl:border-l"
      aria-label="Agents at work"
    >
      <div className="flex items-center justify-between gap-2.5">
        <h2 className="text-[15.5px] font-bold">Agents at work</h2>
        <span className="inline-flex items-center gap-1.5 font-mono text-[10.5px] font-bold tracking-[0.12em] text-positive-deep uppercase">
          <span className="dot dot-green animate-pulse" aria-hidden="true" />
          Live
        </span>
      </div>
      <p className="mt-[7px] border-b border-line pb-3.5 text-[12.5px] leading-normal text-ink-soft">
        Every action your team takes on real vendor sites, in real time.
      </p>

      <ul className="pt-2.5 pb-1.5">
        {agents.map((agent) => (
          <li key={agent.name} className="flex items-center gap-2.5 py-[7px]">
            <span className={`dot dot-${agent.tone}`} aria-hidden="true" />
            <span className="w-[104px] shrink-0 text-[13.5px] font-semibold">{agent.name}</span>
            <span className="flex-1 font-mono text-[11px] leading-[1.4] text-ink-soft">{agent.status}</span>
          </li>
        ))}
      </ul>

      <div className="mt-2 border-t border-line pt-4">
        <h3 className="eyebrow">Activity</h3>
        <ul className="mt-3.5 flex flex-col gap-[18px]">
          {activity.map((item) => (
            <li key={item.id} className="flex gap-2.5">
              <span
                className={`relative mt-0.5 size-[15px] shrink-0 rounded-full border-[1.5px] ${RING_BY_TONE[item.tone]}`}
                aria-hidden="true"
              >
                <span className={`absolute inset-[3.5px] rounded-full ${FILL_BY_TONE[item.tone]}`} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2.5">
                  <span className={`text-[12.5px] font-semibold ${NAME_BY_TONE[item.tone]}`}>
                    {item.agent}
                  </span>
                  <span className="font-mono text-[10.5px] whitespace-nowrap text-ink-faint">
                    {item.timeAgo}
                  </span>
                </div>
                <p className="mt-[3px] text-[12.5px] leading-normal text-ink-soft">{item.description}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
