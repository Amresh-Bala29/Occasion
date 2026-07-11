"use client";

import Link from "next/link";

import { useEvent } from "@/hooks/useEvent";
import type { ApprovalItem } from "@/types";

/** One decision waiting on the organizer. Deciding updates the shared event store. */
export function ApprovalCard({ item }: { item: ApprovalItem }) {
  const { approve, decline } = useEvent();

  return (
    <article className="card relative flex flex-col justify-between gap-3.5 overflow-hidden py-[18px] pr-6 pl-[26px] md:flex-row md:gap-7">
      <span className="absolute inset-y-0 left-0 w-1 bg-warn" aria-hidden="true" />
      <div>
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="eyebrow text-ink">{item.kind}</span>
          <span className="text-line-strong" aria-hidden="true">
            •
          </span>
          <span className="inline-flex items-center gap-1.5 text-[12px] text-ink-soft">
            <span className={`dot dot-${item.agentTone}`} aria-hidden="true" />
            {item.agent}
          </span>
          <span className="chip chip-amber">{item.tag}</span>
        </div>
        <h3 className="mt-2.5 text-[15.5px] font-semibold">{item.title}</h3>
        <p className="mt-1.5 max-w-[62ch] text-[13.5px] leading-[1.55] text-ink-soft">{item.description}</p>
        <div className="mt-3.5 flex items-center gap-2.5">
          <button type="button" className="btn btn-primary" onClick={() => approve(item.id)}>
            Approve
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => decline(item.id)}>
            Decline
          </button>
          <Link
            href={item.threadId ? `/dashboard/messages?thread=${item.threadId}` : "/dashboard/messages"}
            className="px-1 py-2 text-[13px] text-ink-soft hover:underline"
          >
            View thread
          </Link>
        </div>
      </div>
      <div className="order-first shrink-0 md:order-none md:text-right">
        <span className="font-mono text-[21px] font-bold tracking-[-0.01em]">{item.amount}</span>
        <span className="mt-[5px] block font-mono text-[11.5px] text-ink-faint">{item.vendor}</span>
      </div>
    </article>
  );
}
