"use client";

// Settings page content: editable event details beside the spending rules that
// govern what Occasion may do on its own. Spending rules read and write the shared
// useEvent store so the sidebar guardrail stays in sync; event details persist via a
// PATCH and a router refresh so every server-rendered surface picks up the change.
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useEvent } from "@/hooks/useEvent";
import { updateEventDetails } from "@/lib/api";
import type { EventOverview, SpendingRule } from "@/types";

export function ApprovalsPanel({ event }: { event: EventOverview }) {
  return (
    <main className="mx-auto flex w-full max-w-[1010px] flex-col px-6 pt-[22px] pb-10">
      <h1 className="font-serif text-[28px] font-medium tracking-[-0.01em]">Settings</h1>
      <p className="mt-1.5 mb-[22px] text-[14px] text-ink-soft">
        Control your event details and how Occasion spends on your behalf.
      </p>

      <div className="grid grid-cols-1 items-start gap-7 lg:grid-cols-2">
        <div>
          <h2 className="mb-[13px] text-[16px] font-semibold">Event details</h2>
          <EventDetailsCard event={event} />
        </div>

        <div>
          <h2 className="mb-[13px] text-[16px] font-semibold">Spending rules</h2>
          <SpendingRulesCard />
        </div>
      </div>
    </main>
  );
}

/** The event's user-owned descriptors, with an inline edit mode that persists on save. */
function EventDetailsCard({ event }: { event: EventOverview }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({
    name: event.name,
    kind: event.kind,
    date: event.date,
    location: event.location,
    headcount: event.headcount,
  });

  // headcount and date are free-text columns ("320", "TBD", "Aug 6"), so every field edits as text.
  const fields: { key: keyof typeof draft; label: string }[] = [
    { key: "name", label: "Event name" },
    { key: "kind", label: "Type" },
    { key: "date", label: "Date" },
    { key: "location", label: "Location" },
    { key: "headcount", label: "Guest count" },
  ];

  function startEditing() {
    // Re-seed from the prop so edits start from the freshest server values.
    setDraft({
      name: event.name,
      kind: event.kind,
      date: event.date,
      location: event.location,
      headcount: event.headcount,
    });
    setEditing(true);
  }

  async function save() {
    // Send only the fields the user actually changed: a partial PATCH leaves untouched
    // values alone (e.g. the curated short name the backend syncs from `name`).
    const patch: Partial<typeof draft> = {};
    for (const key of Object.keys(draft) as (keyof typeof draft)[]) {
      if (draft[key] !== event[key]) patch[key] = draft[key];
    }
    if (Object.keys(patch).length === 0) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await updateEventDetails(event.id, patch);
      // Refresh so the topbar, sidebar label, and summary card pick up the edit.
      router.refresh();
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card p-5">
      <div className="flex flex-col gap-[13px]">
        {fields.map((field) => (
          <div key={field.key} className="flex items-center justify-between gap-4">
            <span className="text-[13px] text-ink-soft">{field.label}</span>
            {editing ? (
              <input
                type="text"
                value={draft[field.key]}
                onChange={(e) => setDraft((prev) => ({ ...prev, [field.key]: e.target.value }))}
                aria-label={field.label}
                className="w-[190px] rounded-[8px] border border-line-strong px-2 py-1 text-right text-[13.5px] font-semibold"
              />
            ) : (
              // Read straight from the prop so server refreshes (agent edits, intake
              // handoff) show through; the draft only exists while editing.
              <span className="text-[13.5px] font-semibold">{event[field.key]}</span>
            )}
          </div>
        ))}
      </div>

      <button
        type="button"
        className={`btn mt-5 w-full ${editing ? "btn-primary" : "btn-secondary"}`}
        onClick={() => (editing ? save() : startEditing())}
        disabled={saving}
      >
        {editing ? (saving ? "Saving…" : "Save changes") : "Edit details"}
      </button>
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
