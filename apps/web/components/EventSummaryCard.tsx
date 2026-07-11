import { ProgressRing } from "@/components/ProgressRing";
import type { EventOverview } from "@/types";

export function EventSummaryCard({ event }: { event: EventOverview }) {
  const meta = [
    { label: "Date", value: event.date },
    { label: "Location", value: event.location },
    { label: "Headcount", value: event.headcount },
    { label: "Days to go", value: event.daysToGo },
  ];

  return (
    <section
      className="card flex flex-col items-start gap-7 p-[22px] md:flex-row md:items-center md:justify-between md:px-[30px] md:py-[26px]"
      aria-label="Event summary"
    >
      <div>
        <div className="flex items-center gap-2.5">
          <span className="eyebrow text-ink">{event.kind}</span>
          <span className="text-line-strong" aria-hidden="true">
            •
          </span>
          <span className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-positive-deep">
            <span className="dot dot-green" aria-hidden="true" />
            {event.statusLabel}
          </span>
        </div>
        <h1 className="mt-2.5 mb-[18px] font-serif text-[34px] leading-[1.15] font-medium tracking-[-0.01em]">
          {event.name}
        </h1>
        <dl className="flex flex-wrap gap-x-9 gap-y-3">
          {meta.map((item) => (
            <div key={item.label}>
              <dt className="font-mono text-[10px] font-semibold tracking-[0.14em] text-ink-faint uppercase">
                {item.label}
              </dt>
              <dd className="mt-[5px] text-[15px] font-semibold">{item.value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <ProgressRing percent={event.percentComplete} />
    </section>
  );
}
