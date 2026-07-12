import type { BudgetOverview, VendorOverview } from "@/types";

interface MetricCardsProps {
  budget: BudgetOverview;
  vendors: VendorOverview;
  approvalsCount: number;
}

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

/** The three overview stat cards: budget, vendors, pending approvals. */
export function MetricCards({ budget, vendors, approvalsCount }: MetricCardsProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[1.55fr_1fr_1fr]">
      <BudgetCard budget={budget} />

      <section className="card flex flex-col px-5 py-[18px]" aria-label="Vendors confirmed">
        <h2 className="text-[13.5px] font-semibold">Vendors confirmed</h2>
        <div className="mt-3 flex items-baseline gap-[7px]">
          <span className="text-[26px] leading-none font-bold tracking-[-0.02em]">{vendors.confirmed}</span>
          <span className="font-mono text-[13.5px] text-ink-faint">/ {vendors.total}</span>
        </div>
        <p className="mt-2.5 text-[12.5px] text-ink-soft">{vendors.inProgress} in progress</p>
      </section>

      <ApprovalsCard count={approvalsCount} />
    </div>
  );
}

function ApprovalsCard({ count }: { count: number }) {
  // Zero pending flips the card from amber "act now" to green "all clear".
  const toneClass = count === 0 ? "text-positive-deep" : "text-warn-strong";

  return (
    <section className="card flex flex-col px-5 py-[18px]" aria-label="Pending approvals">
      <h2 className="text-[13.5px] font-semibold">Pending approvals</h2>
      <div className="mt-3 flex items-baseline gap-[7px]">
        <span className={`text-[26px] leading-none font-bold tracking-[-0.02em] ${toneClass}`}>
          {count}
        </span>
        <span className="font-mono text-[13.5px] text-ink-faint">{count === 1 ? "item" : "items"}</span>
      </div>
      <p className={`mt-2.5 text-[12.5px] font-semibold ${toneClass}`}>
        {count === 0 ? "All clear" : "Needs your decision"}
      </p>
    </section>
  );
}

function BudgetCard({ budget }: { budget: BudgetOverview }) {
  const committed = budget.paidUsd + budget.pendingUsd;
  const remaining = budget.totalUsd - committed;
  // A just-created event has no budget yet; show 0%, not NaN%.
  const committedPercent = budget.totalUsd > 0 ? Math.round((committed / budget.totalUsd) * 100) : 0;
  const widthOf = (amount: number) => (budget.totalUsd > 0 ? `${(amount / budget.totalUsd) * 100}%` : "0%");

  return (
    <section className="card flex flex-col px-5 py-[18px]" aria-label="Budget committed">
      <div className="flex items-baseline justify-between gap-2.5">
        <h2 className="text-[13.5px] font-semibold">Budget committed</h2>
        <span className="font-mono text-[11px] whitespace-nowrap text-ink-faint">
          {committedPercent}% of {usd.format(budget.totalUsd)}
        </span>
      </div>
      <div className="mt-3 flex items-baseline gap-[7px]">
        <span className="text-[26px] leading-none font-bold tracking-[-0.02em]">{usd.format(committed)}</span>
        <span className="font-mono text-[13.5px] text-ink-faint">/ {usd.format(budget.totalUsd)}</span>
      </div>
      <div
        className="mt-3.5 flex h-2 gap-[3px]"
        role="img"
        aria-label={`${committedPercent}% of budget committed`}
      >
        <span className="min-w-2 rounded-full bg-positive" style={{ width: widthOf(budget.paidUsd) }} />
        <span className="min-w-2 rounded-full bg-brand" style={{ width: widthOf(budget.pendingUsd) }} />
        <span className="min-w-2 flex-1 rounded-full bg-[#e5e9f2]" />
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        <BudgetLegendItem dotClass="dot-green" label={`${usd.format(budget.paidUsd)} paid`} />
        <BudgetLegendItem dotClass="dot-blue" label={`${usd.format(budget.pendingUsd)} pending`} />
        <BudgetLegendItem dotClass="dot-gray" label={`${usd.format(remaining)} left`} />
      </div>
    </section>
  );
}

function BudgetLegendItem({ dotClass, label }: { dotClass: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] text-ink-soft">
      <span className={`dot ${dotClass} size-[7px]`} aria-hidden="true" />
      {label}
    </span>
  );
}
