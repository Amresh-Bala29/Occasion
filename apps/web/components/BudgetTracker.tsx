import { getBudgetDetail, getDashboardData } from "@/lib/api";
import type { BudgetCategory, SavingSuggestion } from "@/types";

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

/** The Budget page: stat cards, per-category spend, and suggested savings. */
export function BudgetTracker() {
  const { budget } = getDashboardData();
  const detail = getBudgetDetail();

  const committed = budget.paidUsd + budget.pendingUsd;
  const committedPercent = Math.round((committed / budget.totalUsd) * 100);
  const paidVendors = detail.categories.filter((category) => category.paidUsd > 0).length;

  const stats = [
    { label: "Total budget", value: usd.format(budget.totalUsd), sub: "Set at kickoff" },
    {
      label: "Committed",
      value: usd.format(committed),
      sub: `${committedPercent}% of budget`,
      valueClass: "text-brand",
    },
    {
      label: "Paid to date",
      value: usd.format(budget.paidUsd),
      sub: `${paidVendors} vendors`,
      valueClass: "text-positive",
    },
    {
      label: "Remaining",
      value: usd.format(budget.totalUsd - committed),
      sub: "Unallocated + pending",
    },
  ];

  return (
    <main className="mx-auto flex w-full max-w-[1010px] flex-col px-6 pt-[22px] pb-10">
      <h1 className="font-serif text-[28px] font-medium tracking-[-0.01em]">Budget</h1>
      <p className="mt-1.5 text-[14px] text-ink-soft">
        A live ledger. The Budget agent tracks every committed and paid dollar against your $85,000
        cap.
      </p>

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((stat) => (
          <StatCard key={stat.label} {...stat} />
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.5fr_1fr]">
        <section aria-label="Spend by category">
          <h2 className="mb-[13px] text-[16px] font-semibold">By category</h2>
          <div className="card px-5 pt-1.5 pb-3.5">
            {detail.categories.map((category) => (
              <CategoryRow key={category.name} category={category} totalUsd={budget.totalUsd} />
            ))}
          </div>
        </section>

        <section aria-label="Suggested savings">
          <h2 className="mb-[13px] text-[16px] font-semibold">Suggested savings</h2>
          <div className="flex flex-col gap-3">
            {detail.savings.map((saving) => (
              <SavingCard key={saving.title} saving={saving} />
            ))}
            <div className="rounded-[12px] border border-brand-mist bg-brand-soft px-[18px] py-[15px]">
              <p className="text-[12.5px] leading-[1.5] text-[#3a424e]">
                {emphasizeSavedAmount(detail.savingsFootnote)}
              </p>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

interface StatCardProps {
  label: string;
  value: string;
  sub: string;
  valueClass?: string;
}

function StatCard({ label, value, sub, valueClass = "" }: StatCardProps) {
  return (
    <section className="card rounded-[16px] px-5 py-[18px]" aria-label={label}>
      <h2 className="text-[12.5px] font-semibold text-ink-soft">{label}</h2>
      <div className={`mt-2 text-[26px] leading-none font-bold tracking-[-0.02em] ${valueClass}`}>
        {value}
      </div>
      <p className="mt-1.5 text-[11.5px] text-ink-faint">{sub}</p>
    </section>
  );
}

function CategoryRow({ category, totalUsd }: { category: BudgetCategory; totalUsd: number }) {
  // Segment widths are shares of the whole budget so bars compare across rows.
  const paidPercent = (category.paidUsd / totalUsd) * 100;
  const pendingPercent = ((category.committedUsd - category.paidUsd) / totalUsd) * 100;

  return (
    <div className="border-t border-line py-3.5 first:border-t-0">
      <div className="flex items-center justify-between">
        <span className="text-[13.5px] font-semibold">{category.name}</span>
        <span className="font-mono text-[12.5px] font-semibold">
          {category.estimate ? "~" : ""}
          {usd.format(category.committedUsd)}
        </span>
      </div>
      <div
        className="mt-[9px] flex h-[7px] overflow-hidden rounded-[5px] bg-[#eef0f4]"
        role="img"
        aria-label={`${usd.format(category.paidUsd)} paid of ${usd.format(category.committedUsd)} committed`}
      >
        <span className="bg-positive" style={{ width: `${paidPercent}%` }} />
        <span className="bg-brand" style={{ width: `${pendingPercent}%` }} />
      </div>
      <p className="mt-1.5 text-[11.5px] text-ink-faint">{categoryDetail(category)}</p>
    </div>
  );
}

function categoryDetail(category: BudgetCategory): string {
  if (category.paidUsd > 0) {
    return `${usd.format(category.paidUsd)} paid · ${usd.format(category.committedUsd - category.paidUsd)} scheduled`;
  }
  if (category.estimate) {
    return `${usd.format(category.committedUsd)} estimated · still sourcing`;
  }
  return `${usd.format(category.committedUsd)} committed · not yet paid`;
}

function SavingCard({ saving }: { saving: SavingSuggestion }) {
  return (
    <div className="card rounded-[12px] border-l-[3px] border-l-positive px-[18px] py-[15px]">
      <div className="flex items-center justify-between">
        <span className="text-[13.5px] font-semibold">{saving.title}</span>
        <span className="font-mono text-[13px] font-semibold text-positive">{saving.amount}</span>
      </div>
      <p className="mt-[5px] text-[12.5px] leading-[1.45] text-ink-soft">{saving.note}</p>
    </div>
  );
}

/** Bolds the "$X under budget" phrase inside the savings footnote. */
function emphasizeSavedAmount(footnote: string) {
  const match = footnote.match(/\$[\d,]+ under budget/);
  if (!match || match.index === undefined) return footnote;
  const end = match.index + match[0].length;
  return (
    <>
      {footnote.slice(0, match.index)}
      <strong>{match[0]}</strong>
      {footnote.slice(end)}
    </>
  );
}
