"use client";

import { useState } from "react";

import type { EventPlan, Milestone, PlanPhase, PlanTaskGroup, RiskItem, Tone } from "@/types";

const DOT_CLASS: Record<Tone, string> = {
  green: "dot-green",
  blue: "dot-blue",
  amber: "dot-amber",
  gray: "dot-gray",
};

/** The plan panel: a phases/tasks/risks/milestones board. */
export function TaskBoard({ plan }: { plan: EventPlan }) {
  // Checkbox state lives here so the "X / Y done" counter tracks toggles.
  const [taskDone, setTaskDone] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(plan.groups.flatMap((group) => group.tasks.map((task) => [task.id, task.done]))),
  );

  function toggleTask(id: string) {
    setTaskDone((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  const totalCount = Object.keys(taskDone).length;
  const doneCount = Object.values(taskDone).filter(Boolean).length;

  return (
    <main className="mx-auto flex w-full max-w-[1010px] flex-col px-6 pt-[22px] pb-10">
      <div className="max-w-[1000px]">
        <PlanHeader />

        <PhasesCard phases={plan.phases} />

        <div className="mt-6 grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.5fr_1fr]">
          <section aria-label="Task checklist">
            <div className="mb-[13px] flex items-center justify-between">
              <h2 className="text-[16px] font-semibold">Task checklist</h2>
              <span className="font-mono text-[11.5px] text-ink-faint">
                {doneCount} / {totalCount} done
              </span>
            </div>
            <div className="flex flex-col gap-[18px]">
              {plan.groups.map((group) => (
                <TaskGroupCard key={group.name} group={group} taskDone={taskDone} onToggle={toggleTask} />
              ))}
            </div>
          </section>

          <div className="flex flex-col gap-5">
            <RisksCard risks={plan.risks} />
            <MilestonesCard milestones={plan.milestones} />
          </div>
        </div>
      </div>
    </main>
  );
}

function PlanHeader() {
  return (
    <div>
      <h1 className="font-serif text-[28px] font-medium tracking-[-0.01em]">Event plan</h1>
      <p className="mt-1.5 text-[14px] text-ink-soft">
        Occasion generated this plan from your requirements and keeps it in sync as agents complete
        work.
      </p>
    </div>
  );
}

function PhasesCard({ phases }: { phases: PlanPhase[] }) {
  const overall = Math.round(phases.reduce((sum, phase) => sum + phase.percent, 0) / phases.length);

  return (
    <section className="card mt-6 rounded-[16px] px-6 py-[22px]" aria-label="Plan phases">
      <div className="mb-[18px] flex items-center justify-between">
        <h2 className="text-[13px] font-semibold text-ink-soft">Phases</h2>
        <span className="font-mono text-[11.5px] text-ink-faint">
          {phases.length} phases · {overall}% overall
        </span>
      </div>
      <div className="grid grid-cols-3 gap-x-2.5 gap-y-4 md:grid-cols-6">
        {phases.map((phase) => (
          <PhaseColumn key={phase.name} phase={phase} />
        ))}
      </div>
    </section>
  );
}

function PhaseColumn({ phase }: { phase: PlanPhase }) {
  const fillClass = phase.percent === 100 ? "bg-positive" : phase.percent === 0 ? "bg-[#c9ced8]" : "bg-brand";

  return (
    <div>
      <div
        className="h-[6px] overflow-hidden rounded-[4px] bg-[#eef0f4]"
        role="img"
        aria-label={`${phase.name}: ${phase.percent}% complete`}
      >
        <div className={`h-full ${fillClass}`} style={{ width: `${phase.percent}%` }} />
      </div>
      <div className="mt-[9px] flex items-center gap-1.5">
        <span className={`dot size-[7px] ${fillClass}`} aria-hidden="true" />
        <span className="text-[12.5px] font-semibold">{phase.name}</span>
      </div>
      <div className="mt-0.5 pl-[13px] font-mono text-[10.5px] text-ink-faint">{phase.note}</div>
    </div>
  );
}

function TaskGroupCard({
  group,
  taskDone,
  onToggle,
}: {
  group: PlanTaskGroup;
  taskDone: Record<string, boolean>;
  onToggle: (id: string) => void;
}) {
  return (
    <div className="card px-[18px] pt-1.5 pb-2.5">
      <div className="flex items-center gap-2 pt-[13px] pb-1">
        <span className={`dot size-[7px] ${DOT_CLASS[group.tone]}`} aria-hidden="true" />
        <span className="text-[13.5px] font-semibold">{group.name}</span>
        <span className="font-mono text-[10px] text-ink-mist">{group.owner}</span>
      </div>
      {group.tasks.map((task) => (
        <TaskRow
          key={task.id}
          label={task.label}
          done={!!taskDone[task.id]}
          onToggle={() => onToggle(task.id)}
        />
      ))}
    </div>
  );
}

function TaskRow({ label, done, onToggle }: { label: string; done: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={done}
      className="flex w-full cursor-pointer items-center gap-[11px] border-t border-[#f2f4f7] py-2 text-left"
    >
      <span
        className={`flex size-[18px] shrink-0 items-center justify-center rounded-[6px] border-[1.5px] text-[11px] text-white ${
          done ? "border-brand bg-brand" : "border-[#cfd5e0] bg-white"
        }`}
        aria-hidden="true"
      >
        {done ? "✓" : ""}
      </span>
      <span className={`text-[13.5px] ${done ? "text-ink-faint line-through" : ""}`}>{label}</span>
    </button>
  );
}

function RisksCard({ risks }: { risks: RiskItem[] }) {
  return (
    <section aria-label="Risk assessment">
      <h2 className="mb-[13px] text-[16px] font-semibold">Risk assessment</h2>
      <div className="card divide-y divide-[#f2f4f7] px-[18px] py-1">
        {risks.map((risk) => (
          <div key={risk.title} className="py-3.5">
            <div className="flex items-center gap-2">
              <span className={riskChipClass(risk.level)}>{risk.level}</span>
              <span className="text-[13.5px] font-semibold">{risk.title}</span>
            </div>
            <p className="mt-1.5 text-[12.5px] leading-[1.45] text-ink-soft">{risk.mitigation}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function riskChipClass(level: RiskItem["level"]): string {
  if (level === "Low") return "chip chip-green text-[9.5px]";
  if (level === "Medium") return "chip chip-amber text-[9.5px]";
  return "chip chip-red text-[9.5px]";
}

function MilestonesCard({ milestones }: { milestones: Milestone[] }) {
  return (
    <section aria-label="Milestones">
      <h2 className="mb-[13px] text-[16px] font-semibold">Milestones</h2>
      <div className="card divide-y divide-[#f2f4f7] px-[18px] py-1">
        {milestones.map((milestone) => (
          <div key={milestone.title} className="flex items-center gap-[11px] py-3">
            <span
              className={`flex size-4 shrink-0 items-center justify-center rounded-full border-[1.5px] text-[9px] text-white ${
                milestone.done ? "border-positive bg-positive" : "border-[#cfd5e0] bg-white"
              }`}
              aria-hidden="true"
            >
              {milestone.done ? "✓" : ""}
            </span>
            <span
              className={`flex-1 text-[13px] font-medium ${milestone.done ? "text-ink" : "text-ink-soft"}`}
            >
              {milestone.title}
            </span>
            <span className="font-mono text-[10.5px] text-ink-faint">{milestone.when}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
