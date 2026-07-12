"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { EVENT_COOKIE, getEvents } from "@/lib/api";
import type { EventOverview } from "@/types";

type SortKey = "edited" | "name" | "progress";
type ViewMode = "grid" | "list";

const SORT_OPTIONS = [
  { value: "edited", label: "Last edited" },
  { value: "name", label: "Name" },
  { value: "progress", label: "Progress" },
];

/** Soft washes cycled across thumbnails so neighboring projects read distinct. */
const THUMB_WASHES = [
  "linear-gradient(135deg, #dfe7fb 0%, #efe7f7 55%, #fde8ee 100%)",
  "linear-gradient(135deg, #e6f4e9 0%, #e4f0fb 60%, #dfe7fb 100%)",
  "linear-gradient(135deg, #fdf3dd 0%, #fbe9e2 55%, #f6e3ef 100%)",
  "linear-gradient(135deg, #e8e9fd 0%, #dff0f8 55%, #e4f6ee 100%)",
];

/**
 * The workspace-level project browser: every event Occasion is coordinating,
 * searchable and filterable. Opening a project sets the active-event cookie
 * (the dashboard's server pages read it) and drops into the dashboard.
 */
export default function ProjectsPage() {
  const router = useRouter();
  const [events, setEvents] = useState<EventOverview[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("edited");
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("all");
  const [location, setLocation] = useState("all");
  const [view, setView] = useState<ViewMode>("grid");

  useEffect(() => {
    let cancelled = false;
    setEvents(null);
    setLoadError(null);
    getEvents()
      .then((rows) => {
        if (cancelled) return;
        setEvents(rows);
        router.prefetch("/dashboard"); // opening a project should land instantly
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : "Something went wrong loading projects.");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey, router]);

  const projects = useMemo(() => {
    if (!events) return [];
    const needle = query.trim().toLowerCase();
    const rows = events.filter(
      (event) =>
        (kind === "all" || event.kind === kind) &&
        (status === "all" || event.statusLabel === status) &&
        (location === "all" || event.location === location) &&
        (needle === "" ||
          `${event.name} ${event.kind} ${event.location}`.toLowerCase().includes(needle)),
    );
    if (sort === "name") rows.sort((a, b) => a.name.localeCompare(b.name));
    if (sort === "progress") rows.sort((a, b) => b.percentComplete - a.percentComplete);
    return rows;
  }, [events, query, sort, kind, status, location]);

  function openProject(eventId: string) {
    // Not httpOnly on purpose: the client sets it, server components read it.
    document.cookie = `${EVENT_COOKIE}=${encodeURIComponent(eventId)}; path=/; max-age=31536000`;
    router.push("/dashboard");
  }

  const loading = events === null && loadError === null;

  return (
    <div className="min-h-screen bg-surface">
      <header className="mx-auto flex w-full max-w-[1400px] items-center justify-between px-6 py-5 md:px-10">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="relative size-[30px] shrink-0 rounded-[9px] bg-brand" aria-hidden="true">
            <span className="absolute inset-[9px] rounded-full border-[2.5px] border-white" />
          </span>
          <span className="text-[16.5px] font-bold tracking-[-0.01em]">Occasion</span>
        </Link>
        <Link
          href="/dashboard"
          className="text-[13.5px] font-semibold text-ink-soft hover:text-ink hover:underline"
        >
          Back to dashboard →
        </Link>
      </header>

      <main className="mx-auto w-full max-w-[1400px] px-6 pb-16 md:px-10">
        <div className="mt-2 flex items-center justify-between gap-4">
          <h1 className="text-[28px] font-bold tracking-[-0.01em]">Projects</h1>
          <Link
            href="/ask?new=1"
            className="flex items-center gap-2 rounded-[10px] border border-line-strong bg-surface px-4 py-2.5 text-[13.5px] font-semibold hover:bg-[#f6f8fc]"
          >
            Create
            <ChevronDown className="text-ink-faint" />
          </Link>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2.5">
          <label className="relative min-w-[220px] flex-1">
            <svg
              className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-ink-faint"
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              aria-hidden="true"
            >
              <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M9.5 9.5L13 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search projects…"
              aria-label="Search projects"
              className="w-full rounded-[10px] border border-line-strong bg-surface py-2.5 pr-3.5 pl-9 text-[13.5px] font-medium placeholder:text-ink-faint hover:border-[#c3cbdd]"
            />
          </label>

          <FilterSelect
            label="Sort by"
            value={sort}
            onChange={(value) => setSort(value as SortKey)}
            options={SORT_OPTIONS}
          />
          <FilterSelect
            label="Filter by type"
            value={kind}
            onChange={setKind}
            options={filterOptions("Any type", events, (event) => event.kind)}
          />
          <FilterSelect
            label="Filter by status"
            value={status}
            onChange={setStatus}
            options={filterOptions("Any status", events, (event) => event.statusLabel)}
          />
          <FilterSelect
            label="Filter by location"
            value={location}
            onChange={setLocation}
            options={filterOptions("All locations", events, (event) => event.location)}
          />

          <ViewToggle view={view} onChange={setView} />
        </div>

        {loadError && (
          <div className="mt-8 rounded-[14px] border border-[#f3c6c6] bg-danger-soft px-5 py-4">
            <p className="text-[13.5px] font-semibold text-danger">Couldn&apos;t load projects</p>
            <p className="mt-1 text-[13px] text-ink-soft">{loadError}</p>
            <button
              type="button"
              className="btn btn-secondary mt-3"
              onClick={() => setReloadKey((key) => key + 1)}
            >
              Try again
            </button>
          </div>
        )}

        {loading && <ProjectsSkeleton />}

        {events && events.length === 0 && (
          <div className="mt-8 rounded-[14px] border border-line bg-canvas px-6 py-10 text-center">
            <p className="text-[15px] font-semibold">No projects yet</p>
            <p className="mx-auto mt-1.5 max-w-[44ch] text-[13.5px] text-ink-soft">
              Tell Occasion what you&apos;re planning and it spins up the project, the plan, and the
              agents to run it.
            </p>
            <Link href="/ask?new=1" className="btn btn-primary mt-4 inline-block">
              New Project
            </Link>
          </div>
        )}

        {events && events.length > 0 && (
          <section className="mt-8">
            <h2 className="text-[14.5px] font-bold">Active in last 14 days</h2>
            {projects.length === 0 ? (
              <p className="mt-4 text-[13.5px] text-ink-soft">No projects match your filters.</p>
            ) : view === "grid" ? (
              <div className="mt-4 grid grid-cols-1 gap-x-6 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
                {projects.map((event, index) => (
                  <ProjectCard
                    key={event.id}
                    event={event}
                    wash={THUMB_WASHES[index % THUMB_WASHES.length]}
                    onOpen={() => openProject(event.id)}
                  />
                ))}
              </div>
            ) : (
              <div className="mt-4 divide-y divide-line overflow-hidden rounded-[14px] border border-line">
                {projects.map((event, index) => (
                  <ProjectRow
                    key={event.id}
                    event={event}
                    wash={THUMB_WASHES[index % THUMB_WASHES.length]}
                    onOpen={() => openProject(event.id)}
                  />
                ))}
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

/** "All" plus every distinct value of one event field, for a filter dropdown. */
function filterOptions(
  allLabel: string,
  events: EventOverview[] | null,
  pick: (event: EventOverview) => string,
): { value: string; label: string }[] {
  const values = [...new Set((events ?? []).map(pick))];
  return [{ value: "all", label: allLabel }, ...values.map((value) => ({ value, label: value }))];
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <span className="relative">
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="cursor-pointer appearance-none rounded-[10px] border border-line-strong bg-surface py-2.5 pr-8 pl-3.5 text-[13.5px] font-medium hover:border-[#c3cbdd]"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-ink-faint" />
    </span>
  );
}

function ViewToggle({ view, onChange }: { view: ViewMode; onChange: (view: ViewMode) => void }) {
  const buttons: { mode: ViewMode; label: string; icon: React.ReactNode }[] = [
    {
      mode: "grid",
      label: "Grid view",
      icon: (
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <rect x="1.5" y="1.5" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.5" />
          <rect x="7.9" y="1.5" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.5" />
          <rect x="1.5" y="7.9" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.5" />
          <rect x="7.9" y="7.9" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      ),
    },
    {
      mode: "list",
      label: "List view",
      icon: (
        <svg width="14" height="12" viewBox="0 0 14 12" fill="none" aria-hidden="true">
          <circle cx="1.4" cy="2" r="1.1" fill="currentColor" />
          <circle cx="1.4" cy="6" r="1.1" fill="currentColor" />
          <circle cx="1.4" cy="10" r="1.1" fill="currentColor" />
          <path d="M4.5 2h8M4.5 6h8M4.5 10h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      ),
    },
  ];

  return (
    <span className="ml-auto flex gap-2">
      {buttons.map(({ mode, label, icon }) => (
        <button
          key={mode}
          type="button"
          aria-label={label}
          aria-pressed={view === mode}
          onClick={() => onChange(mode)}
          className={`flex size-[38px] cursor-pointer items-center justify-center rounded-[10px] border ${
            view === mode
              ? "border-ink bg-ink text-white"
              : "border-line-strong text-ink-soft hover:bg-[#f6f8fc]"
          }`}
        >
          {icon}
        </button>
      ))}
    </span>
  );
}

function ProjectCard({
  event,
  wash,
  onOpen,
}: {
  event: EventOverview;
  wash: string;
  onOpen: () => void;
}) {
  return (
    <button type="button" onClick={onOpen} className="group block w-full cursor-pointer text-left">
      <span className="block overflow-hidden rounded-[14px] border border-line shadow-card transition-all duration-200 group-hover:-translate-y-0.5 group-hover:border-[#c3cbdd]">
        <ProjectThumb event={event} wash={wash} />
      </span>
      <span className="mt-3 flex items-center gap-3 px-0.5">
        <Monogram name={event.name} />
        <span className="min-w-0">
          <span className="block truncate text-[15px] font-semibold">{event.name}</span>
          <span className="mt-0.5 block text-[12.5px] text-ink-soft">
            {event.statusLabel} · {event.daysToGo}
          </span>
        </span>
      </span>
    </button>
  );
}

/** A miniature "site preview" built from event data, standing in for a screenshot. */
function ProjectThumb({ event, wash }: { event: EventOverview; wash: string }) {
  return (
    <span className="flex aspect-[16/10] w-full flex-col bg-surface">
      <span className="block px-4 pt-3 pb-4" style={{ background: wash }}>
        <span className="flex items-center justify-between">
          <span className="flex items-center gap-1">
            <span className="size-[7px] rounded-[2px] bg-brand" aria-hidden="true" />
            <span className="text-[7px] font-bold tracking-tight">{event.shortName}</span>
          </span>
          <span className="flex items-center gap-1.5" aria-hidden="true">
            <span className="h-[3px] w-3 rounded bg-ink/20" />
            <span className="h-[3px] w-3 rounded bg-ink/20" />
            <span className="rounded-full bg-ink px-1.5 py-[2px] text-[6px] font-semibold text-white">
              Open
            </span>
          </span>
        </span>

        <span className="mt-3.5 block text-center">
          <span className="block font-mono text-[6.5px] font-semibold tracking-[0.16em] text-ink-soft uppercase">
            {event.kind}
          </span>
          <span className="mx-auto mt-1 block max-w-[26ch] font-serif text-[15px] leading-[1.15] font-medium tracking-[-0.01em] line-clamp-2">
            {event.name}
          </span>
          <span className="mt-1 block text-[7.5px] text-ink-soft">
            {event.location} · {event.date}
          </span>
          <span className="mx-auto mt-2.5 block h-[5px] w-24 overflow-hidden rounded-full bg-[#00000014]">
            <span
              className="block h-full rounded-full bg-brand"
              style={{ width: `${event.percentComplete}%` }}
            />
          </span>
          <span className="mt-1 block font-mono text-[6.5px] font-semibold tracking-[0.1em] text-ink-soft uppercase">
            {event.percentComplete}% planned
          </span>
        </span>
      </span>

      <span className="flex flex-1 items-center px-4" aria-hidden="true">
        <span className="grid w-full grid-cols-3 gap-2">
          {["#3b5bdb", "#37b24d", "#f59f00"].map((dot) => (
            <span
              key={dot}
              className="rounded-[7px] border border-[#00000012] bg-white px-2 py-2 shadow-[0_1px_2px_rgba(23,32,58,0.05)]"
            >
              <span className="block size-2 rounded-full" style={{ background: dot }} />
              <span className="mt-1.5 block h-[3px] w-3/4 rounded bg-[#e3e6ee]" />
              <span className="mt-1 block h-[3px] w-1/2 rounded bg-[#edeff4]" />
            </span>
          ))}
        </span>
      </span>
    </span>
  );
}

function ProjectRow({
  event,
  wash,
  onOpen,
}: {
  event: EventOverview;
  wash: string;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full cursor-pointer items-center gap-4 bg-surface px-4 py-3 text-left hover:bg-[#f6f8fc]"
    >
      <span
        className="relative h-12 w-[76px] shrink-0 overflow-hidden rounded-[8px] border border-line"
        style={{ background: wash }}
        aria-hidden="true"
      >
        <span className="absolute inset-x-2.5 top-2 bottom-0 rounded-t-[4px] bg-white/85" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[14px] font-semibold">{event.name}</span>
        <span className="mt-0.5 block truncate text-[12px] text-ink-soft">
          {event.kind} · {event.location}
        </span>
      </span>
      <span className="chip chip-gray hidden sm:inline-block">{event.statusLabel}</span>
      <span className="hidden w-28 text-right text-[12.5px] text-ink-soft md:block">{event.date}</span>
      <span className="w-12 text-right text-[12.5px] font-semibold">{event.percentComplete}%</span>
    </button>
  );
}

function Monogram({ name }: { name: string }) {
  const letters = name
    .split(/\s+/)
    .filter((word) => /[A-Za-z0-9]/.test(word))
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join("");

  return (
    <span
      className="flex size-[38px] shrink-0 items-center justify-center rounded-full bg-ink text-[12.5px] font-bold text-white"
      aria-hidden="true"
    >
      {letters || "?"}
    </span>
  );
}

function ProjectsSkeleton() {
  return (
    <div className="mt-8 grid animate-pulse grid-cols-1 gap-x-6 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
      {[0, 1, 2].map((slot) => (
        <div key={slot}>
          <div className="aspect-[16/10] rounded-[14px] bg-[#eceff5]" />
          <div className="mt-3 flex items-center gap-3">
            <div className="size-[38px] rounded-full bg-[#eceff5]" />
            <div className="flex-1">
              <div className="h-3.5 w-1/2 rounded bg-[#eceff5]" />
              <div className="mt-2 h-3 w-1/3 rounded bg-[#eceff5]" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ChevronDown({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="10"
      height="6"
      viewBox="0 0 10 6"
      fill="none"
      aria-hidden="true"
    >
      <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}
