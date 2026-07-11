"use client";

// Approvals page content: pending decisions and the decision log on the left,
// editable spending rules on the right. Everything reads and writes the shared
// useEvent store so the sidebar guardrail and overview stay in sync.
import { useState } from "react";

import { ApprovalCard } from "@/components/ApprovalCard";
import { useEvent } from "@/hooks/useEvent";
import type { DecisionRecord, SpendingRule } from "@/types";

export function ApprovalsPanel() {
  const { approvals, decisions } = useEvent();

  return (
    <main className="mx-auto flex w-full max-w-[1010px] flex-col px-6 pt-[22px] pb-10">
      <div className="grid grid-cols-1 items-start gap-7 lg:grid-cols-[1.6fr_1fr]">
        <div>
          <h1 className="font-serif text-[28px] font-medium tracking-[-0.01em]">Approvals</h1>
          <p className="mt-1.5 mb-[22px] text-[14px] text-ink-soft">
            Agents prepare everything autonomously and pause here for anything that spends money or
            is otherwise sensitive.
          </p>

          <div className="mb-[13px] flex items-center gap-2.5">
            <h2 className="text-[16px] font-semibold">Pending</h2>
            {approvals.length > 0 && <span className="chip chip-amber">{approvals.length}</span>}
          </div>
          {approvals.length > 0 ? (
            <div className="flex flex-col gap-3">
              {approvals.map((item) => (
                <ApprovalCard key={item.id} item={item} />
              ))}
            </div>
          ) : (
            <NothingPending />
          )}

          <h2 className="mt-[26px] mb-[13px] text-[16px] font-semibold">Recent decisions</h2>
          <section className="card divide-y divide-line px-[18px] py-1" aria-label="Recent decisions">
            {decisions.map((decision) => (
              <DecisionRow key={decision.id} decision={decision} />
            ))}
          </section>
        </div>

        <div className="lg:sticky lg:top-[80px]">
          <h2 className="mb-[13px] text-[16px] font-semibold">Spending rules</h2>
          <SpendingRulesCard />
        </div>
      </div>
    </main>
  );
}

function NothingPending() {
  return (
    <div className="card px-5 py-[30px] text-center">
      <span
        className="inline-flex size-[34px] items-center justify-center rounded-full bg-positive-soft text-[17px] text-positive-deep"
        aria-hidden="true"
      >
        ✓
      </span>
      <p className="mt-2.5 text-[15px] font-semibold">Nothing pending</p>
      <p className="mt-1 text-[13px] text-ink-soft">
        {"You're all caught up. Recent decisions are logged on the right."}
      </p>
    </div>
  );
}

function DecisionRow({ decision }: { decision: DecisionRecord }) {
  return (
    <div className="flex items-center gap-[13px] py-[13px]">
      <span
        className={`flex size-[18px] shrink-0 items-center justify-center rounded-full text-[10px] ${
          decision.approved ? "bg-positive-soft text-positive-deep" : "bg-danger-soft text-danger"
        }`}
        role="img"
        aria-label={decision.approved ? "Approved" : "Declined"}
      >
        {decision.approved ? "✓" : "✕"}
      </span>
      <span className="flex-1 text-[13.5px] font-medium">{decision.title}</span>
      <span className="font-mono text-[12.5px] font-semibold">{decision.amount}</span>
      <span className="w-[62px] text-right font-mono text-[10.5px] text-ink-faint">
        {decision.when}
      </span>
    </div>
  );
}

/** The auto-approve limit and per-action rules, with an inline edit mode. */
function SpendingRulesCard() {
  const { autoApproveLimit, rules, setAutoApproveLimit, toggleRule } = useEvent();
  const [editing, setEditing] = useState(false);

  // The store keeps the limit preformatted ("$500"), so edit on the raw number.
  const limitDollars = Number(autoApproveLimit.replace(/\D/g, ""));

  function handleLimitChange(raw: string) {
    // Parse as a number (not digit-stripping) so "500.5" doesn't become 5005.
    const dollars = Math.max(0, Math.floor(Number(raw) || 0));
    setAutoApproveLimit("$" + dollars.toLocaleString("en-US"));
  }

  return (
    <div className="card p-5">
      <p className="text-[12.5px] leading-[1.5] text-ink-soft">
        Occasion acts on its own below your limit and pauses for approval above it.
      </p>

      <div className="mt-3.5 flex items-baseline gap-2">
        {editing ? (
          <>
            <span className="text-[22px] font-bold tracking-[-0.02em]" aria-hidden="true">
              $
            </span>
            <input
              type="number"
              min={0}
              value={limitDollars}
              onChange={(event) => handleLimitChange(event.target.value)}
              aria-label="Auto-approve limit in dollars"
              className="w-[110px] rounded-[8px] border border-line-strong px-2 py-0.5 text-[22px] font-bold tracking-[-0.02em]"
            />
          </>
        ) : (
          <span className="text-[30px] font-bold tracking-[-0.02em]">{autoApproveLimit}</span>
        )}
        <span className="text-[13px] text-ink-faint">auto-approve limit</span>
      </div>

      <div className="my-[18px] h-px bg-line" aria-hidden="true" />

      <div className="flex flex-col gap-[13px]">
        {rules.map((rule) =>
          editing ? (
            <button
              key={rule.id}
              type="button"
              onClick={() => toggleRule(rule.id)}
              className="-mx-2 -my-1 flex cursor-pointer items-center justify-between rounded-[8px] px-2 py-1 hover:bg-[#f6f8fc]"
            >
              <RuleRow rule={rule} />
            </button>
          ) : (
            <div key={rule.id} className="flex items-center justify-between">
              <RuleRow rule={rule} />
            </div>
          ),
        )}
      </div>

      <button
        type="button"
        className={`btn mt-5 w-full ${editing ? "btn-primary" : "btn-secondary"}`}
        onClick={() => setEditing((prev) => !prev)}
      >
        {editing ? "Done" : "Edit spending rules"}
      </button>
    </div>
  );
}

function RuleRow({ rule }: { rule: SpendingRule }) {
  const auto = rule.value === "Auto";
  return (
    <>
      <span className="text-[13px]">{rule.label}</span>
      <span
        className={`inline-flex items-center gap-1.5 text-[12px] font-semibold ${
          auto ? "text-positive-deep" : "text-warn-deep"
        }`}
      >
        <span className={`dot size-1.5 ${auto ? "dot-green" : "dot-amber"}`} aria-hidden="true" />
        {rule.value}
      </span>
    </>
  );
}
