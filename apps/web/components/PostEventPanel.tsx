"use client";

// Wrap-up queue: tasks Occasion runs automatically after the event, plus the
// performance report placeholder. Pausing a task is client-only until the
// scheduling API lands.
import { useState } from "react";

import type { EventOverview, PostEventTask } from "@/types";

export function PostEventPanel({ event, tasks }: { event: EventOverview; tasks: PostEventTask[] }) {
  const [pausedIds, setPausedIds] = useState<ReadonlySet<string>>(new Set());

  function togglePaused(id: string) {
    setPausedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // "26 days" → "26d" for the countdown tile.
  const daysTile = `${event.daysToGo.match(/^\d+/)?.[0] ?? event.daysToGo}d`;

  return (
    <main className="mx-auto flex w-full max-w-[1000px] flex-col px-6 pt-[22px] pb-10">
      <h1 className="font-serif text-[28px] font-medium tracking-[-0.01em]">Post-event</h1>
      <p className="mt-1.5 text-[14px] text-ink-soft">
        Everything Occasion will handle once the summit wraps — queued and ready to run automatically.
      </p>

      <section
        className="mt-[22px] flex items-center gap-3.5 rounded-[14px] border border-brand-mist bg-brand-soft px-5 py-4"
        aria-label="Wrap-up unlock date"
      >
        <span className="flex size-[38px] shrink-0 items-center justify-center rounded-[10px] bg-brand font-mono text-[13px] font-semibold text-white">
          {daysTile}
        </span>
        <div>
          <p className="text-[14px] font-semibold">Wrap-up unlocks after the event · {event.date}</p>
          <p className="mt-0.5 text-[12.5px] text-ink-soft">
            These tasks activate automatically the morning after. You can adjust any of them now.
          </p>
        </div>
      </section>

      <div className="mt-6 grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.4fr_1fr]">
        <section aria-label="Queued tasks">
          <h2 className="mb-3 text-[16px] font-semibold">Queued tasks</h2>
          <div className="card divide-y divide-line px-[18px] py-1">
            {tasks.map((task) => (
              <QueuedTaskRow
                key={task.id}
                task={task}
                paused={pausedIds.has(task.id)}
                onToggle={() => togglePaused(task.id)}
              />
            ))}
          </div>
        </section>

        <PerformanceReportCard />
      </div>
    </main>
  );
}

function QueuedTaskRow({
  task,
  paused,
  onToggle,
}: {
  task: PostEventTask;
  paused: boolean;
  onToggle: () => void;
}) {
  const chipClass = paused ? "chip-amber" : task.state === "Draft ready" ? "chip-green" : "chip-gray";

  return (
    <div className="flex items-start gap-[13px] py-[15px]">
      <span
        className="flex size-[30px] shrink-0 items-center justify-center rounded-[8px] bg-brand-soft font-mono text-[11px] font-semibold text-brand"
        aria-hidden="true"
      >
        {task.glyph}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] font-semibold">{task.title}</p>
        <p className="mt-0.5 text-[12px] text-ink-soft">{task.description}</p>
      </div>
      <span className={`chip ${chipClass}`}>{paused ? "Paused" : task.state}</span>
      <button
        type="button"
        onClick={onToggle}
        className="cursor-pointer text-[12px] text-ink-faint hover:text-ink"
        aria-label={paused ? `Resume ${task.title}` : `Pause ${task.title}`}
      >
        {paused ? "Resume" : "Pause"}
      </button>
    </div>
  );
}

function PerformanceReportCard() {
  return (
    <section aria-label="Performance report">
      <h2 className="mb-3 text-[16px] font-semibold">Performance report</h2>
      <div className="card p-[22px] text-center">
        <div
          className="flex h-[120px] items-center justify-center rounded-[10px]"
          style={{
            background: "repeating-linear-gradient(135deg, #f4f6fa, #f4f6fa 9px, #eef1f6 9px, #eef1f6 18px)",
          }}
        >
          <span className="font-mono text-[11px] text-ink-mist">report generates post-event</span>
        </div>
        <p className="mt-4 text-[13px] leading-[1.5] text-ink-soft">
          Final budget reconciliation, vendor scorecards, attendance, and feedback — compiled into a
          shareable summary.
        </p>
        {/* Disabled by design: the report only exists once the event has run. */}
        <button
          type="button"
          disabled
          title="The report compiles the morning after the event wraps."
          className="mt-4 w-full cursor-not-allowed rounded-[10px] border border-line-strong bg-white p-2.5 text-[13px] font-semibold text-ink-mist"
        >
          Available Aug 7
        </button>
      </div>
    </section>
  );
}
