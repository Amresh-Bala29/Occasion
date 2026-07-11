"use client";

import { useState } from "react";
import { getVendors } from "@/lib/api";
import type { Vendor, VendorStatus } from "@/types";

type VendorFilter = "All" | VendorStatus;

const FILTERS: VendorFilter[] = ["All", "Confirmed", "Awaiting you", "Negotiating", "Sourcing"];

/** Dot + label classes per status; label follows the deep-tone convention from the exemplars. */
const STATUS_STYLES: Record<VendorStatus, { dot: string; text: string }> = {
  Confirmed: { dot: "dot-green", text: "text-positive-deep" },
  "Awaiting you": { dot: "dot-amber", text: "text-warn-deep" },
  Negotiating: { dot: "dot-blue", text: "text-brand" },
  Sourcing: { dot: "dot-gray", text: "text-ink-soft" },
};

// Shared column template so the header and rows always stay aligned.
const GRID_COLS = "grid-cols-[2.2fr_1.1fr_0.9fr] md:grid-cols-[2.2fr_1.1fr_0.8fr_1fr_0.9fr]";

/** The vendors tab: status filters over the full vendor table, plus ad-hoc category sourcing. */
export function VendorsPanel() {
  const [vendors, setVendors] = useState<Vendor[]>(getVendors);
  const [filter, setFilter] = useState<VendorFilter>("All");
  const [addingCategory, setAddingCategory] = useState(false);

  const countFor = (f: VendorFilter) =>
    f === "All" ? vendors.length : vendors.filter((v) => v.status === f).length;
  const visible = filter === "All" ? vendors : vendors.filter((v) => v.status === filter);

  const addCategory = (category: string) => {
    setVendors((current) => [...current, sourcingPlaceholder(category)]);
    setAddingCategory(false);
  };

  return (
    <main className="mx-auto flex w-full max-w-[1010px] flex-col px-6 pt-[22px] pb-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-[28px] font-medium tracking-[-0.01em]">Vendors</h1>
          <p className="mt-1.5 text-[14px] text-ink-soft">
            {vendors.length} vendors across the event · agents are sourcing, negotiating and
            booking on your behalf.
          </p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={() => setAddingCategory((open) => !open)}>
          + Add category
        </button>
      </div>

      {addingCategory && (
        <AddCategoryForm onAdd={addCategory} onCancel={() => setAddingCategory(false)} />
      )}

      <div className="mt-[22px] mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter vendors by status">
        {FILTERS.map((f) => (
          <FilterChip
            key={f}
            label={f}
            count={countFor(f)}
            active={filter === f}
            onSelect={() => setFilter(f)}
          />
        ))}
      </div>

      <section className="card overflow-hidden rounded-[16px]" aria-label="Vendor list">
        <div
          className={`grid ${GRID_COLS} gap-3 border-b border-[#eef0f4] bg-[#fafbfc] px-[22px] py-3 font-mono text-[10px] tracking-[0.07em] text-ink-faint uppercase`}
        >
          <span>Vendor</span>
          <span>Status</span>
          <span className="hidden md:block">Quotes</span>
          <span className="hidden md:block">Last activity</span>
          <span className="text-right">Cost</span>
        </div>
        {visible.length === 0 ? (
          <p className="py-10 text-center text-[13px] text-ink-faint">No vendors in this state.</p>
        ) : (
          <div className="divide-y divide-[#eef0f4]">
            {visible.map((vendor) => (
              <VendorRow key={vendor.id} vendor={vendor} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

function FilterChip({
  label,
  count,
  active,
  onSelect,
}: {
  label: string;
  count: number;
  active: boolean;
  onSelect: () => void;
}) {
  const tone = active
    ? "border-brand bg-brand-soft text-brand-deep"
    : "border-line bg-surface text-ink-soft";
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={`inline-flex cursor-pointer items-center gap-[7px] rounded-full border px-[13px] py-[7px] text-[12.5px] font-semibold ${tone}`}
    >
      {label}
      <span className="font-mono text-[10.5px] opacity-70">{count}</span>
    </button>
  );
}

function VendorRow({ vendor }: { vendor: Vendor }) {
  const status = STATUS_STYLES[vendor.status];
  return (
    <div className={`grid ${GRID_COLS} items-center gap-3 px-[22px] py-3.5`}>
      <div className="flex min-w-0 items-center gap-[13px]">
        <span
          className="flex size-9 flex-none items-center justify-center rounded-[9px] bg-[#f1f3f8] font-mono text-[12px] font-semibold text-ink-soft"
          aria-hidden="true"
        >
          {vendor.initials}
        </span>
        <div className="min-w-0">
          <div className="truncate text-[14px] font-semibold">{vendor.name}</div>
          <div className="truncate text-[11.5px] text-ink-faint">{vendor.category}</div>
        </div>
      </div>
      <span className={`inline-flex items-center gap-1.5 text-[12px] font-semibold ${status.text}`}>
        <span className={`dot ${status.dot} size-1.5`} aria-hidden="true" />
        {vendor.status}
      </span>
      <span className="hidden text-[13px] text-ink-soft md:block">{vendor.quotes}</span>
      <span className="hidden text-[12.5px] text-ink-faint md:block">{vendor.lastActivity}</span>
      <span className="text-right font-mono text-[13.5px] font-semibold">{vendor.cost}</span>
    </div>
  );
}

function AddCategoryForm({
  onAdd,
  onCancel,
}: {
  onAdd: (category: string) => void;
  onCancel: () => void;
}) {
  const [category, setCategory] = useState("");

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = category.trim();
    if (trimmed) onAdd(trimmed);
  };

  return (
    <form onSubmit={submit} className="card mt-4 flex flex-wrap items-center gap-2.5 px-4 py-3">
      <input
        autoFocus
        value={category}
        onChange={(event) => setCategory(event.target.value)}
        placeholder="Category name, e.g. Florals"
        aria-label="New vendor category name"
        className="min-w-0 flex-1 rounded-[9px] border border-line-strong bg-surface px-3 py-2 text-[13px] placeholder:text-ink-mist"
      />
      <button type="submit" className="btn btn-primary" disabled={!category.trim()}>
        Add
      </button>
      <button type="button" className="btn btn-secondary" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}

/** A just-created category starts as an agent-driven sourcing search with nothing booked yet. */
function sourcingPlaceholder(category: string): Vendor {
  return {
    id: `vendor-new-${Date.now()}`,
    initials: category.slice(0, 2).toUpperCase(),
    name: `New ${category} search`,
    category,
    status: "Sourcing",
    quotes: 0,
    lastActivity: "just now",
    cost: "—",
  };
}
