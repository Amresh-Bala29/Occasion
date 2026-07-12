"use client";

import Link from "next/link";

import { ApprovalCard } from "@/components/ApprovalCard";
import { EventSummaryCard } from "@/components/EventSummaryCard";
import { MetricCards } from "@/components/MetricCards";
import { Topbar } from "@/components/Topbar";
import { useEvent } from "@/hooks/useEvent";
import type { DashboardData, DeadlineItem, Vendor, VendorStatus } from "@/types";

interface EventDashboardProps {
  data: DashboardData;
  vendors: Vendor[];
  deadlines: DeadlineItem[];
}

/** Overview page content; the sidebar and agent rail come from the dashboard layout. */
export function EventDashboard({ data, vendors, deadlines }: EventDashboardProps) {
  // Approvals come from the shared store so deciding one updates every panel.
  const { approvals } = useEvent();

  return (
    <>
      <Topbar section="Overview" eventName={data.event.name} agentsWorking={data.agentsWorking} />

      <main className="mx-auto flex w-full max-w-[1010px] flex-col gap-4 px-6 pt-[22px] pb-10">
        <EventSummaryCard event={data.event} />

        <MetricCards budget={data.budget} vendors={data.vendors} approvalsCount={approvals.length} />

        <section className="mt-2 flex flex-col gap-3.5" aria-label="Pending approvals">
          <div className="flex items-center gap-2.5">
            <h2 className="text-[16px] font-semibold tracking-[-0.01em]">Waiting on you</h2>
            {approvals.length > 0 && <span className="chip chip-amber">{approvals.length} pending</span>}
          </div>
          {approvals.length > 0 ? (
            <div className="flex flex-col gap-3.5">
              {approvals.map((item) => (
                <ApprovalCard key={item.id} item={item} />
              ))}
            </div>
          ) : (
            <AllCaughtUpCard />
          )}
        </section>

        <section className="mt-3 grid gap-5 lg:grid-cols-[1.55fr_1fr]" aria-label="Vendors and key deadlines">
          <VendorsPreview vendors={vendors} />
          <KeyDeadlines deadlines={deadlines} />
        </section>
      </main>
    </>
  );
}

/** Empty state shown once every pending approval has been decided. */
function AllCaughtUpCard() {
  return (
    <div className="card px-5 py-[30px] text-center">
      <span
        className="inline-flex size-[34px] items-center justify-center rounded-full bg-positive-soft text-[17px] text-positive-deep"
        aria-hidden="true"
      >
        ✓
      </span>
      <p className="mt-2.5 text-[15px] font-semibold">All caught up</p>
      <p className="mt-[3px] text-[13px] text-ink-soft">
        Occasion will surface the next decision here when it needs you.
      </p>
    </div>
  );
}

/** Dot + label color for each vendor status; the dot inherits via bg-current. */
const VENDOR_STATUS_COLOR: Record<VendorStatus, string> = {
  Confirmed: "text-positive-deep",
  "Awaiting you": "text-warn-deep",
  Negotiating: "text-brand-deep",
  Sourcing: "text-ink-soft",
};

function VendorsPreview({ vendors }: { vendors: Vendor[] }) {
  return (
    <div>
      <div className="mb-[13px] flex items-center justify-between">
        <h2 className="text-[16px] font-semibold tracking-[-0.01em]">Vendors</h2>
        <Link href="/dashboard/vendors" className="text-[13px] font-semibold text-brand hover:underline">
          View all {vendors.length}
        </Link>
      </div>
      <div className="card divide-y divide-line overflow-hidden rounded-[14px]">
        {vendors.slice(0, 6).map((vendor) => (
          <VendorRow key={vendor.id} vendor={vendor} />
        ))}
      </div>
    </div>
  );
}

function VendorRow({ vendor }: { vendor: Vendor }) {
  return (
    <div className="flex items-center justify-between px-[18px] py-3.5">
      <div className="flex min-w-0 items-center gap-[13px]">
        <span
          className="flex size-[34px] shrink-0 items-center justify-center rounded-[9px] bg-[#f1f3f8] font-mono text-[12px] font-semibold text-ink-soft"
          aria-hidden="true"
        >
          {vendor.initials}
        </span>
        <div className="min-w-0">
          <div className="text-[14px] font-semibold">{vendor.name}</div>
          <div className="text-[11.5px] text-ink-faint">{vendor.category}</div>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <span
          className={`inline-flex items-center gap-1.5 text-[12px] font-semibold ${VENDOR_STATUS_COLOR[vendor.status]}`}
        >
          <span className="size-1.5 shrink-0 rounded-full bg-current" aria-hidden="true" />
          {vendor.status}
        </span>
        <span className="min-w-[66px] text-right font-mono text-[13px] font-semibold">{vendor.cost}</span>
      </div>
    </div>
  );
}

function KeyDeadlines({ deadlines }: { deadlines: DeadlineItem[] }) {
  return (
    <div>
      <div className="mb-[13px] flex items-center justify-between">
        <h2 className="text-[16px] font-semibold tracking-[-0.01em]">Key deadlines</h2>
        <Link href="/dashboard/calendar" className="text-[13px] font-semibold text-brand hover:underline">
          Calendar
        </Link>
      </div>
      <div className="card divide-y divide-line px-[18px]">
        {deadlines.map((deadline) => (
          <DeadlineRow key={deadline.id} deadline={deadline} />
        ))}
      </div>
    </div>
  );
}

function DeadlineRow({ deadline }: { deadline: DeadlineItem }) {
  const metaColor = deadline.emphasis === "urgent" ? "text-warn-strong" : "text-ink-faint";
  const dayColor = deadline.emphasis === "event" ? "text-brand" : "";

  return (
    <div className="flex items-center gap-3.5 py-[13px]">
      <div className="w-[46px] shrink-0 text-center">
        <div className={`font-mono text-[10px] tracking-[0.06em] uppercase ${metaColor}`}>{deadline.month}</div>
        <div className={`text-[20px] leading-none font-bold tracking-[-0.02em] ${dayColor}`}>{deadline.day}</div>
      </div>
      <span className="h-[30px] w-px shrink-0 bg-line" aria-hidden="true" />
      <div className="min-w-0">
        <div className="text-[13.5px] font-semibold">{deadline.title}</div>
        <div className={`text-[11.5px] ${metaColor}`}>{deadline.meta}</div>
      </div>
    </div>
  );
}
