"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

/* ------------------------------------------------------------------ */
/* Content — every fact below is sourced from the actual codebase     */
/* ------------------------------------------------------------------ */

const TABS = [
  { id: "product", label: "Product" },
  { id: "how", label: "How it works" },
  { id: "capabilities", label: "Capabilities" },
  { id: "safety", label: "Safety" },
  { id: "demo", label: "Demo" },
  { id: "about", label: "About" },
];

const HERO_STATS = [
  { value: 13, label: "specialist agents", detail: "one per slice of event production" },
  { value: 19, label: "routable roster", detail: "specialists + web agents + workflows" },
  { value: 6, label: "vendor categories", detail: "researched in parallel waves" },
  { value: 1, label: "agent allowed to check out", detail: "purchasing — and only purchasing" },
];

const PILLARS = [
  {
    title: "Does, not suggests",
    body: "Twelve of thirteen agents drive a real signed-in cloud Chrome — Gmail, Google Calendar, Luma — the way a human assistant would. One logged-in profile stands in for a pile of per-service API keys.",
  },
  {
    title: "Shows receipts",
    body: "Every browser run returns an Agent View replay you can watch click by click, and agents must cite the URL of the page where they verified every claim. A listing without its URL doesn't count as published.",
  },
  {
    title: "Asks before it binds",
    body: "Research is autonomous; bookings, deposits, and contracts pause for you. Your approval words are quoted verbatim inside the task before any agent is allowed to act on them.",
  },
];

const MARQUEE_ITEMS = [
  "Luma",
  "Partiful",
  "Eventbrite",
  "Meetup",
  "Gmail",
  "Google Calendar",
  "4imprint",
  "vendor sites everywhere",
];

const PIPELINE_STEPS = [
  {
    n: "01",
    name: "Brief",
    body: "The requirements agent interviews you into a 15-field structured spec — headcount to dietary restrictions to priorities in your own words. No browser needed.",
  },
  {
    n: "02",
    name: "Plan",
    body: "A deep model synthesizes the full event plan: timeline, per-category budget, deadlines with consequences, staffing, backups, and a scored risk register.",
  },
  {
    n: "03",
    name: "Source",
    body: "Six category agents research live vendor sites in waves of three — deep research runs bounded at 40 minutes and 80 steps — then merge into a ranked shortlist.",
  },
  {
    n: "04",
    name: "Outreach",
    body: "Up to two vendors per category get a personalized inquiry — by form when one exists, signed-in Gmail otherwise — because a single quote can't be compared.",
  },
  {
    n: "05",
    name: "Approve",
    body: "Anything binding pauses on your dashboard. An empty approval string throws an error: bookings are binding commitments, so your words ride inside the task.",
  },
  {
    n: "06",
    name: "Execute",
    body: "The purchasing agent completes the checkout, listings go live with their public URLs recorded, and every session leaves a watchable Agent View replay.",
  },
];

const RUNTIME_CHIPS = [
  { text: 'task: "Find caterers near Pier 27"', tone: "plain" },
  { text: "RouteDecision { reason → agent }", tone: "brand" },
  { text: "occasion-catering", tone: "plain" },
  { text: "H cloud Chrome · ≤80 steps · ≤40 min", tone: "plain" },
  { text: "CateringPlan ✓ schema-validated", tone: "green" },
  { text: "Agent View replay", tone: "brand" },
];

/* Orbit layout: 8 agents on the outer ring, 5 on the inner. */
const FLEET_OUTER = [
  "venue",
  "catering",
  "staffing",
  "entertainment",
  "decorations",
  "merchandise",
  "purchasing",
  "scheduling",
];
const FLEET_INNER = ["budget", "marketing", "distribution", "requirements", "post-event"];

const CAPABILITIES = [
  {
    name: "Venues, end to end",
    body: "Searches marketplaces, checks capacity and rules, requests tours, compares options — and books only after your approval, with the confirmation URL recorded.",
    meta: "deep model · 80 steps · 40 min",
  },
  {
    name: "Catering that shows its math",
    body: "Food and beverage quantities computed from headcount and duration, dietary restrictions carried through every quote — arithmetic included in the answer.",
    meta: "40 vegan covers? recalculated",
  },
  {
    name: "Purchasing with a tradeoff statement",
    body: "Before spending a dollar it writes the tradeoff down: price vs budget cap, shipping vs event deadline, refund policy, backup supplier. Then it acts.",
    meta: "the only agent that checks out",
  },
  {
    name: "Merch against the calendar",
    body: "Custom-branded products quoted as production time plus shipping time versus your event date — expedited options priced when the math gets tight.",
    meta: "deadline-first quoting",
  },
  {
    name: "Distribution with playbooks",
    body: "Publishes listings to Luma, Partiful, Eventbrite, and Meetup using per-platform posting procedures, records each live URL, and one platform's failure never stops the rest.",
    meta: "4 platform skills baked in",
  },
  {
    name: "Outreach that never double-nudges",
    body: "Follow-ups read the Gmail thread first. A vendor who already replied gets their quote extracted verbatim — never a second nudge, never a re-submitted form.",
    meta: "thread-aware by design",
  },
  {
    name: "A plan that audits itself",
    body: "Risks are scored likelihood × impact, and the engine derives ones nobody typed: run $4,000 over cap and that becomes a High risk row on its own.",
    meta: "21-day tight-timeline tripwire",
  },
  {
    name: "Memory that compounds",
    body: "Vendors earn reputation dossiers keyed by their domain. Preferences only ever grow. Finished research files itself for full-text recall, and re-runs resume from snapshots instead of repeating 16-minute browser sessions.",
    meta: "postgres full-text · 4 stores",
  },
];

const GATE_CHECKS = [
  {
    n: "1",
    check: "Irreversible floor",
    detail: "Contracts and private data always require sign-off — even when your rule says Auto.",
    outcome: "always asks",
    tone: "amber" as const,
  },
  {
    n: "2",
    check: "Your rules",
    detail: "Five categories, each toggled Auto or Ask-first. Unconfigured defaults to Ask-first — the system fails strict.",
    outcome: "asks first",
    tone: "amber" as const,
  },
  {
    n: "3",
    check: "Your limit",
    detail: "Purchases and deposits over your auto-approve limit pause with an amber Over-limit flag and the exact reason.",
    outcome: "asks + flags",
    tone: "amber" as const,
  },
  {
    n: "4",
    check: "Inside the fence",
    detail: "Everything else proceeds instantly — no interruption, reason logged as “within your auto-approve rules.”",
    outcome: "auto-approved",
    tone: "green" as const,
  },
];

const SAFETY_CARDS = [
  {
    title: "A sandbox policy, in code",
    body: "Six allow-listed domains and payment-form submission blocked outright — the policy lives in the service's code now: it rides into every agent's prompt as a domain guardrail and maps its blocked actions onto the approval gates, with a host-and-action check ready as enforcement hardens.",
  },
  {
    title: "Guardrails in every prompt",
    body: "Five rules ride with every agent: never pay, sign, or book without approval quoted in the task; respect budget caps; stop cold at logins and CAPTCHAs; never type credentials; cite the URL behind every claim.",
  },
  {
    title: "A three-part paper trail",
    body: "Every gated action leaves a pending approval row, a permanent decision record, and activity-feed lines for both the flag and your verdict — linked back to the vendor email thread it came from.",
  },
  {
    title: "Watchable, always",
    body: "Every session carries an Agent View replay link, agents grade their own runs — success, partial, infeasible, blocked — and failures come back as data, never buried exceptions.",
  },
];

const STACK_ROWS = [
  { k: "agents", v: "H Company computer-use sessions — a deep 122B reasoner for judgment calls, a fast 35B model for procedure" },
  { k: "service", v: "FastAPI + Postgres — a dozen event-scoped reads feed the dashboard its live state" },
  { k: "web", v: "Next.js 16 · React 19 · Tailwind v4 — this page ships zero animation dependencies" },
  { k: "memory", v: "Postgres full-text recall, vendor reputation scores, and user preferences that only grow" },
];

/* ------------------------------------------------------------------ */
/* Hero simulation — a scripted miniature of a real Occasion run       */
/* ------------------------------------------------------------------ */

const SIM_BRIEF = "Company summit — Aug 6 · Pier 27, SF · 320 guests · $85,000 budget";
const SIM_TYPE_START = 500;
const SIM_TYPE_MS = 24;

const SIM_TASKS = [
  { agent: "venue", label: "Tour request — Pier 27", done: "3 venues shortlisted", at: 2400, doneAt: 5600 },
  { agent: "catering", label: "Revised quote — Bi-Rite, 40 vegan", done: "Quote requested", at: 2900, doneAt: 6200 },
  { agent: "merch", label: "350 totes — 4imprint", done: "Artwork uploaded · quote in", at: 3400, doneAt: 6800 },
  { agent: "sched", label: "Sync 6 calendar holds", done: "6 holds on calendar", at: 3900, doneAt: 7400 },
];

const SIM_APPROVAL_AT = 7000;
const SIM_APPROVED_AT = 9200;
const SIM_FADE_AT = 12600;
const SIM_TOTAL = 13400;
const SIM_SHOWCASE = 11500; // frozen frame shown under prefers-reduced-motion
const SIM_TICK = 100;

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function useSimClock(): number {
  const [t, setT] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion()) {
      setT(SIM_SHOWCASE);
      return;
    }
    const id = setInterval(() => setT((prev) => (prev + SIM_TICK) % SIM_TOTAL), SIM_TICK);
    return () => clearInterval(id);
  }, []);
  return t;
}

function HeroSim() {
  const t = useSimClock();
  const typedChars = Math.max(0, Math.min(SIM_BRIEF.length, Math.floor((t - SIM_TYPE_START) / SIM_TYPE_MS)));
  const typing = t >= SIM_TYPE_START && typedChars < SIM_BRIEF.length;
  const approvalShown = t >= SIM_APPROVAL_AT;
  const approved = t >= SIM_APPROVED_AT;
  const fading = t >= SIM_FADE_AT;

  return (
    <>
      <p className="sr-only">
        Animated preview of an Occasion run: an event brief fans out to the venue, catering, merchandise, and
        scheduling agents; an over-limit purchase pauses for approval and proceeds once approved.
      </p>
      <div
        aria-hidden="true"
        className={`card relative overflow-hidden p-0 transition-opacity duration-700 ${fading ? "opacity-0" : "opacity-100"}`}
      >
      {/* window chrome */}
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-[#f2b8b5]" />
        <span className="size-2.5 rounded-full bg-[#f5d9a8]" />
        <span className="size-2.5 rounded-full bg-[#b7e2c0]" />
        <span className="ml-2 font-mono text-[10.5px] tracking-[0.08em] text-ink-soft uppercase">
          occasion — live run
        </span>
        <span className="ml-auto flex items-center gap-1.5 font-mono text-[10px] text-ink-soft">
          <span className="dot dot-green lp-pulse" />
          novaflow-summit-2026
        </span>
      </div>

      <div className="space-y-3 p-4">
        {/* brief being typed */}
        <div className="rounded-[10px] border border-line bg-brand-soft/60 px-3.5 py-3">
          <p className="eyebrow !text-brand-deep">Event brief</p>
          <p className="mt-1.5 min-h-[42px] font-mono text-[12px] leading-[1.6] text-ink">
            {SIM_BRIEF.slice(0, typedChars)}
            {typing && <span className="lp-caret ml-0.5 inline-block h-[13px] w-[7px] bg-brand align-middle" />}
          </p>
        </div>

        {/* agent fan-out */}
        <div className="space-y-1.5">
          {SIM_TASKS.map((task) => {
            const shown = t >= task.at;
            const working = t >= task.at + 450 && t < task.doneAt;
            const done = t >= task.doneAt;
            return (
              <div
                key={task.agent}
                className={`flex items-center gap-2.5 rounded-[9px] border border-line bg-surface px-3 py-2 transition-all duration-500 ${
                  shown ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
                }`}
              >
                <span className={`dot ${done ? "dot-green" : working ? "dot-blue lp-pulse" : "dot-gray"}`} />
                <span className="w-14 shrink-0 font-mono text-[10.5px] font-semibold tracking-[0.06em] text-ink-soft uppercase">
                  {task.agent}
                </span>
                <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">
                  {done ? task.done : task.label}
                </span>
                <span
                  className={`chip ${done ? "chip-green" : working ? "bg-brand-soft text-brand-deep" : "chip-gray"}`}
                >
                  {done ? "done" : working ? "browsing" : "queued"}
                </span>
              </div>
            );
          })}
        </div>

        {/* approval gate */}
        <div className="min-h-[92px]">
          <div
            className={`relative rounded-[10px] border px-3.5 py-3 transition-all duration-500 ${
              approvalShown ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
            } ${approved ? "border-positive/40 bg-positive-soft/50" : "border-warn/40 bg-warn-soft/60"}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[12.5px] font-semibold text-ink">350 custom tote bags — 4imprint</p>
                <p className="mt-0.5 text-[11.5px] text-ink-soft">
                  $2,940 · clears the Aug 4 setup deadline with expedited shipping
                </p>
              </div>
              <span className="chip chip-amber shrink-0">over $500 limit</span>
            </div>
            <div className="mt-2.5 flex items-center gap-2">
              <span
                className={`rounded-[7px] px-3 py-1 text-[11px] font-semibold text-white transition-colors ${
                  approved ? "bg-positive-deep" : "bg-brand"
                }`}
              >
                Approve
              </span>
              <span className="rounded-[7px] border border-line-strong px-3 py-1 text-[11px] font-semibold text-ink-soft">
                Decline
              </span>
              {approved && (
                <span className="lp-stamp ml-auto rounded-[4px] border-2 border-positive-deep px-2 py-0.5 font-mono text-[10px] font-bold tracking-[0.18em] text-positive-deep uppercase">
                  Approved
                </span>
              )}
            </div>
          </div>
        </div>

        {/* budget strip */}
        <div className="rounded-[10px] border border-line bg-surface px-3.5 py-3">
          <div className="flex items-baseline justify-between">
            <p className="eyebrow">Budget committed</p>
            <p className="font-mono text-[11px] text-ink-soft">
              {approved ? "$58.4k" : "$55.5k"} / $85k · {approved ? "7" : "6"}/11 vendors
            </p>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-brand-mist">
            <div
              className="h-full rounded-full bg-brand transition-all duration-[900ms] ease-out"
              style={{ width: approved ? "68%" : "65%" }}
            />
          </div>
          <p className={`mt-2 flex items-center gap-1.5 text-[11px] transition-opacity duration-500 ${approved ? "opacity-100" : "opacity-0"}`}>
            <span className="dot dot-green" />
            <span className="text-ink-soft">You approved — the purchasing agent is proceeding now.</span>
          </p>
        </div>
      </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Shared building blocks                                              */
/* ------------------------------------------------------------------ */

function Count({ to }: { to: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [value, setValue] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let raf = 0;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.disconnect();
        if (prefersReducedMotion()) {
          setValue(to);
          return;
        }
        const start = performance.now();
        const step = (now: number) => {
          const p = Math.min(1, (now - start) / 1100);
          setValue(Math.round(to * (1 - Math.pow(1 - p, 3))));
          if (p < 1) raf = requestAnimationFrame(step);
        };
        raf = requestAnimationFrame(step);
      },
      { threshold: 0.6 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [to]);
  return <span ref={ref}>{value}</span>;
}

function SectionHeading({
  eyebrow,
  title,
  lede,
  dark = false,
}: {
  eyebrow: string;
  title: ReactNode;
  lede?: string;
  dark?: boolean;
}) {
  return (
    <div className="max-w-2xl" data-reveal>
      <p className={`eyebrow ${dark ? "!text-[#8fa0c4]" : ""}`}>{eyebrow}</p>
      <h2
        className={`mt-3 font-serif text-[clamp(30px,4.2vw,46px)] leading-[1.06] font-medium tracking-[-0.015em] ${
          dark ? "text-[#eef1f7]" : "text-ink"
        }`}
      >
        {title}
      </h2>
      {lede && (
        <p className={`mt-4 text-[16px] leading-[1.65] ${dark ? "text-[#a7b2cc]" : "text-ink-soft"}`}>{lede}</p>
      )}
    </div>
  );
}

const CONTAINER = "mx-auto w-full max-w-[1180px] px-6";

/* ------------------------------------------------------------------ */
/* Nav                                                                 */
/* ------------------------------------------------------------------ */

function jumpTo(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth" });
  history.replaceState(null, "", `#${id}`);
  el.focus({ preventScroll: true });
}

function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [active, setActive] = useState(TABS[0].id);
  const [progress, setProgress] = useState(0);
  const linkRefs = useRef<Record<string, HTMLAnchorElement | null>>({});
  const [bar, setBar] = useState({ left: 0, width: 0 });

  useEffect(() => {
    // Nav owns all scroll-derived state so the page sections never re-render
    // while scrolling. Progress is quantized to skip no-op renders.
    const onScroll = () => {
      setScrolled(window.scrollY > 8);
      const doc = document.documentElement;
      const max = doc.scrollHeight - window.innerHeight;
      setProgress(max > 0 ? Math.round(Math.min(1, window.scrollY / max) * 200) / 200 : 0);

      const probe = window.innerHeight * 0.35;
      let current = TABS[0].id;
      for (const tab of TABS) {
        const el = document.getElementById(tab.id);
        if (el && el.getBoundingClientRect().top <= probe) current = tab.id;
      }
      setActive(current);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  const measure = useCallback(() => {
    const el = linkRefs.current[active];
    if (el) setBar({ left: el.offsetLeft, width: el.offsetWidth });
  }, [active]);

  useEffect(() => {
    measure();
    // Web fonts swap in after mount and change every tab's width.
    document.fonts?.ready.then(measure);
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  const jump = (id: string) => (event: React.MouseEvent) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    jumpTo(id);
  };

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 border-b transition-colors duration-300 ${
        scrolled ? "border-line bg-canvas/85 backdrop-blur-md" : "border-transparent bg-transparent"
      }`}
    >
      {/* reading progress */}
      <div className="absolute inset-x-0 top-0 h-[2px]">
        <div className="h-full bg-brand transition-[width] duration-150 ease-out" style={{ width: `${progress * 100}%` }} />
      </div>

      <div className={`${CONTAINER} flex flex-wrap items-center gap-x-6 gap-y-0 py-3`}>
        <a href="#product" onClick={jump("product")} className="font-serif text-[22px] font-medium tracking-[-0.01em]">
          Occasion
        </a>

        <nav
          aria-label="Page sections"
          className="relative order-3 -mx-1 flex w-full items-center gap-1 overflow-x-auto p-1 lg:order-none lg:w-auto"
        >
          {TABS.map((tab) => (
            <a
              key={tab.id}
              href={`#${tab.id}`}
              onClick={jump(tab.id)}
              ref={(el) => {
                linkRefs.current[tab.id] = el;
              }}
              className={`rounded-full px-3 py-1.5 text-[13px] font-medium whitespace-nowrap transition-colors ${
                active === tab.id ? "text-ink" : "text-ink-soft hover:text-ink"
              }`}
            >
              {tab.label}
            </a>
          ))}
          <span
            className="absolute bottom-0 h-[2px] rounded-full bg-brand transition-all duration-300 ease-out"
            style={{ left: bar.left, width: bar.width }}
          />
        </nav>

        <Link href="/ask?new=1" className="btn btn-primary ml-auto whitespace-nowrap">
          Try Occasion
        </Link>
      </div>
    </header>
  );
}

/* ------------------------------------------------------------------ */
/* Sections                                                            */
/* ------------------------------------------------------------------ */

function ProductSection() {
  return (
    <section id="product" tabIndex={-1} className="relative overflow-hidden pt-[128px] pb-20 outline-none md:pt-[150px]">
      {/* dot-grid backdrop, faded at the edges */}
      <div className="lp-dotgrid pointer-events-none absolute inset-0" aria-hidden />
      <div className="lp-blob pointer-events-none absolute -top-24 -right-32 size-[420px] rounded-full bg-brand-mist/70 blur-3xl" aria-hidden />
      <div className="lp-blob-slow pointer-events-none absolute top-64 -left-40 size-[360px] rounded-full bg-brand-soft blur-3xl" aria-hidden />

      <div className={`${CONTAINER} relative`}>
        <div className="grid items-center gap-12 lg:grid-cols-[1.05fr_0.95fr]">
          <div data-reveal>
            <p className="eyebrow flex items-center gap-2">
              <span className="dot dot-green lp-pulse" />
              Autonomous event operations
            </p>
            <h1 className="mt-4 font-serif text-[clamp(42px,6.4vw,72px)] leading-[1.02] font-medium tracking-[-0.02em]">
              An event team that <span className="text-brand">does the work.</span>
            </h1>
            <p className="mt-5 max-w-[520px] text-[17px] leading-[1.65] text-ink-soft">
              Occasion fields thirteen specialist agents that research venues, email caterers, compare quotes, and
              book vendors on real websites — and pause for your approval before anything binding.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link href="/ask?new=1" className="btn btn-primary px-5 py-2.5 text-[14px]">
                Open the dashboard →
              </Link>
              <a
                href="#how"
                onClick={(event) => {
                  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                  event.preventDefault();
                  jumpTo("how");
                }}
                className="btn btn-secondary px-5 py-2.5 text-[14px]"
              >
                See how it works
              </a>
            </div>
            <p className="mt-5 font-mono text-[11px] tracking-[0.06em] text-ink-soft">
              real browser sessions · watchable replays · your spending rules
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-2.5">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-line-strong bg-surface px-3 py-1 font-mono text-[10.5px] font-semibold tracking-[0.06em] text-ink-soft shadow-card whitespace-nowrap">
                <span className="dot dot-blue" />
                Powered by H Company
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-line-strong bg-surface px-3 py-1 font-mono text-[10.5px] font-semibold tracking-[0.06em] text-ink-soft shadow-card whitespace-nowrap">
                <span className="dot dot-green" />
                Powered by Gradium
              </span>
            </div>
          </div>

          <div data-reveal style={{ "--rd": "150ms" } as CSSProperties}>
            <HeroSim />
          </div>
        </div>

        {/* stat band */}
        <div className="mt-20 grid grid-cols-2 gap-px overflow-hidden rounded-[14px] border border-line bg-line lg:grid-cols-4">
          {HERO_STATS.map((stat, i) => (
            <div key={stat.label} className="bg-surface px-6 py-6" data-reveal style={{ "--rd": `${i * 80}ms` } as CSSProperties}>
              <p className="font-serif text-[44px] leading-none font-medium text-ink">
                <Count to={stat.value} />
              </p>
              <p className="mt-2 text-[13.5px] font-semibold text-ink">{stat.label}</p>
              <p className="mt-0.5 text-[12px] text-ink-soft">{stat.detail}</p>
            </div>
          ))}
        </div>

        {/* pillars */}
        <div className="mt-16 grid gap-5 md:grid-cols-3">
          {PILLARS.map((pillar, i) => (
            <div
              key={pillar.title}
              className="lp-lift card p-6"
              data-reveal
              style={{ "--rd": `${i * 90}ms` } as CSSProperties}
            >
              <h2 className="font-serif text-[22px] font-medium text-ink">{pillar.title}</h2>
              <p className="mt-2.5 text-[14px] leading-[1.65] text-ink-soft">{pillar.body}</p>
            </div>
          ))}
        </div>
      </div>

      {/* marquee of surfaces it operates on */}
      <div className="lp-marquee-mask mt-16 border-y border-line bg-surface/60 py-4" data-reveal>
        <div className="lp-marquee flex w-max items-center">
          {[0, 1].map((copy) => (
            <div key={copy} className="flex items-center gap-10 pr-10" aria-hidden={copy === 1}>
              {MARQUEE_ITEMS.map((item) => (
                <span key={item} className="flex items-center gap-10 font-mono text-[12px] tracking-[0.12em] text-ink-soft uppercase">
                  {item}
                  <span className="text-brand" aria-hidden="true">
                    ◆
                  </span>
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PipelineDiagram({ animate }: { animate: boolean }) {
  const nodes = PIPELINE_STEPS.map((step, i) => ({ ...step, x: 60 + i * ((1100 - 120) / (PIPELINE_STEPS.length - 1)) }));
  return (
    <svg viewBox="0 0 1100 130" className="hidden w-full md:block" role="img" aria-label="Six-stage pipeline from brief to execution">
      {/* connector */}
      <line x1="60" y1="52" x2="1040" y2="52" stroke="var(--color-line-strong)" strokeWidth="2" />
      <line x1="60" y1="52" x2="1040" y2="52" stroke="var(--color-brand)" strokeWidth="2" strokeDasharray="6 10" className={animate ? "lp-march" : ""} opacity="0.55" />
      {animate && (
        <>
          <circle r="4.5" fill="var(--color-brand)">
            <animateMotion dur="7s" repeatCount="indefinite" path="M60 52 H1040" />
          </circle>
          {/* hidden until its delayed motion begins, else it parks at the SVG origin */}
          <circle r="4.5" fill="var(--color-brand)" opacity="0">
            <animate attributeName="opacity" values="0;0.5" begin="3.5s" dur="0.2s" fill="freeze" />
            <animateMotion dur="7s" begin="3.5s" repeatCount="indefinite" path="M60 52 H1040" />
          </circle>
        </>
      )}
      {nodes.map((node, i) => {
        const gate = node.name === "Approve";
        return (
          <g key={node.n}>
            <circle cx={node.x} cy="52" r="21" fill="var(--color-surface)" stroke={gate ? "var(--color-warn)" : "var(--color-brand)"} strokeWidth="2" />
            {gate && <circle cx={node.x} cy="52" r="28" fill="none" stroke="var(--color-warn)" strokeWidth="1" opacity="0.4" strokeDasharray="3 5" />}
            <text x={node.x} y="57" textAnchor="middle" fontFamily="var(--font-mono)" fontSize="13" fontWeight="700" fill={gate ? "var(--color-warn-deep)" : "var(--color-brand)"}>
              {node.n}
            </text>
            <text x={node.x} y="102" textAnchor="middle" fontFamily="var(--font-sans)" fontSize="14" fontWeight="600" fill="var(--color-ink)">
              {node.name}
            </text>
            {i < nodes.length - 1 && (
              <text x={node.x + ((1100 - 120) / 5) / 2} y="44" textAnchor="middle" fontFamily="var(--font-mono)" fontSize="9" fill="var(--color-ink-mist)">
                ▸
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function HowSection({ animate }: { animate: boolean }) {
  return (
    <section id="how" tabIndex={-1} className="scroll-mt-28 border-t border-line bg-surface/50 py-24 outline-none lg:scroll-mt-20">
      <div className={CONTAINER}>
        <SectionHeading
          eyebrow="The pipeline"
          title={
            <>
              One brief becomes a <span className="text-brand">run of show.</span>
            </>
          }
          lede="Three chained workflows — plan, source, contact — carry a conversation all the way to booked vendors. Six stages, every one auditable, and the first failure stops the chain while handing back everything already learned."
        />

        <div className="mt-14" data-reveal>
          <PipelineDiagram animate={animate} />
        </div>

        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {PIPELINE_STEPS.map((step, i) => (
            <div key={step.n} className="lp-lift card p-6" data-reveal style={{ "--rd": `${i * 70}ms` } as CSSProperties}>
              <div className="flex items-baseline justify-between">
                <span className={`font-mono text-[13px] font-bold ${step.name === "Approve" ? "text-warn-deep" : "text-brand"}`}>
                  {step.n}
                </span>
                <span className="h-px flex-1 mx-3 bg-line" />
                <h3 className="text-[16px] font-semibold text-ink">{step.name}</h3>
              </div>
              <p className="mt-3 text-[13.5px] leading-[1.65] text-ink-soft">{step.body}</p>
            </div>
          ))}
        </div>

        {/* runtime anatomy — the router must show its work */}
        <div className="mt-14 overflow-hidden rounded-[14px] border border-line bg-ink text-white" data-reveal>
          <div className="border-b border-white/10 px-6 py-3">
            <p className="eyebrow !text-[#8fa0c4]">Under the hood — one task, end to end</p>
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-3 px-6 py-6">
            {RUNTIME_CHIPS.map((chip, i) => (
              <span key={chip.text} className="flex items-center gap-2">
                <span
                  className={`rounded-[8px] border px-3 py-1.5 font-mono text-[11.5px] ${
                    chip.tone === "brand"
                      ? "border-brand/60 bg-brand/15 text-[#aebffb]"
                      : chip.tone === "green"
                        ? "border-positive/50 bg-positive/10 text-[#8fdba0]"
                        : "border-white/15 bg-white/5 text-[#c8d1e6]"
                  }`}
                >
                  {chip.text}
                </span>
                {i < RUNTIME_CHIPS.length - 1 && (
                  <span aria-hidden="true" className="lp-arrow font-mono text-[13px] text-[#5c6b93]">
                    →
                  </span>
                )}
              </span>
            ))}
          </div>
          <p className="border-t border-white/10 px-6 py-4 text-[13px] leading-[1.6] text-[#a7b2cc]">
            The routing schema declares <span className="font-mono text-[12px] text-[#aebffb]">reason</span> before{" "}
            <span className="font-mono text-[12px] text-[#aebffb]">agent</span> — the router must justify its pick before
            it's allowed to make one. And failures return as data, never exceptions: a stopped run still hands back every
            stage report, session id, and replay link it collected.
          </p>
        </div>
      </div>
    </section>
  );
}

function OrbitDiagram() {
  return (
    <div className="relative mx-auto hidden h-[460px] w-full max-w-[520px] sm:block" aria-hidden>
      {/* rings */}
      <div className="absolute top-1/2 left-1/2 size-[400px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-line-strong/70" />
      <div className="absolute top-1/2 left-1/2 size-[248px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-dashed border-line-strong/70" />

      {/* hub */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
        <div className="relative grid size-[104px] place-items-center rounded-full border border-brand/30 bg-surface shadow-card">
          <div className="lp-ping absolute inset-0 rounded-full border border-brand/40" />
          <div className="lp-ping-late absolute inset-0 rounded-full border border-brand/30" />
          <div className="text-center">
            <p className="font-mono text-[10px] font-bold tracking-[0.14em] text-brand uppercase">orchestrator</p>
            <p className="mt-0.5 font-mono text-[9px] text-ink-soft">reason → agent</p>
          </div>
        </div>
      </div>

      {/* orbiting agents */}
      {FLEET_OUTER.map((name, i) => (
        <div
          key={name}
          className="lp-orbit-cw absolute top-1/2 left-1/2 origin-top-left"
          style={{ "--a": `${(360 / FLEET_OUTER.length) * i}deg`, "--r": "200px" } as CSSProperties}
        >
          <span className="block rounded-full border border-line-strong bg-surface px-3 py-1 font-mono text-[10.5px] font-semibold tracking-[0.06em] text-ink-soft shadow-card whitespace-nowrap">
            {name}
          </span>
        </div>
      ))}
      {FLEET_INNER.map((name, i) => (
        <div
          key={name}
          className="lp-orbit-ccw absolute top-1/2 left-1/2 origin-top-left"
          style={{ "--a": `${(360 / FLEET_INNER.length) * i}deg`, "--r": "124px" } as CSSProperties}
        >
          <span className="block rounded-full border border-brand-mist bg-brand-soft px-3 py-1 font-mono text-[10.5px] font-semibold tracking-[0.06em] text-brand-deep whitespace-nowrap">
            {name}
          </span>
        </div>
      ))}
    </div>
  );
}

function CapabilitiesSection() {
  return (
    <section id="capabilities" tabIndex={-1} className="scroll-mt-28 py-24 outline-none lg:scroll-mt-20">
      <div className={CONTAINER}>
        <div className="grid items-center gap-10 lg:grid-cols-[1fr_1.1fr]">
          <div>
            <SectionHeading
              eyebrow="The fleet"
              title={
                <>
                  Thirteen specialists, <span className="text-brand">one job each.</span>
                </>
              }
              lede="Declared in the exact order an event unfolds — from the requirements interview through venue, catering, staffing, and entertainment to post-event thank-yous. An LLM router reads the full 19-member roster and justifies every dispatch."
            />
            {/* sm:sr-only keeps the roster in the accessibility tree once the orbit (aria-hidden) takes over */}
            <div className="mt-6 flex flex-wrap gap-2 sm:sr-only" data-reveal>
              {[...FLEET_OUTER, ...FLEET_INNER].map((name) => (
                <span key={name} className="chip chip-gray">
                  {name}
                </span>
              ))}
            </div>
            <p className="mt-8 hidden text-[13px] text-ink-soft sm:block" data-reveal>
              Plus three managed web agents — <span className="font-mono text-[12px]">web-surfer</span>,{" "}
              <span className="font-mono text-[12px]">web-scraper</span>,{" "}
              <span className="font-mono text-[12px]">deep-search</span> — for the work no specialist owns.
            </p>
          </div>
          <div data-reveal>
            <OrbitDiagram />
          </div>
        </div>

        <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {CAPABILITIES.map((cap, i) => (
            <div key={cap.name} className="lp-lift card flex flex-col p-5" data-reveal style={{ "--rd": `${(i % 4) * 70}ms` } as CSSProperties}>
              <h3 className="text-[15px] font-semibold text-ink">{cap.name}</h3>
              <p className="mt-2 flex-1 text-[13px] leading-[1.6] text-ink-soft">{cap.body}</p>
              <p className="mt-3 border-t border-line pt-2.5 font-mono text-[10px] tracking-[0.08em] text-ink-soft uppercase">
                {cap.meta}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function SafetySection() {
  return (
    <section id="safety" tabIndex={-1} className="scroll-mt-28 bg-[#141b2f] py-24 text-white outline-none lg:scroll-mt-20">
      <div className={CONTAINER}>
        <SectionHeading
          dark
          eyebrow="The gate"
          title={
            <>
              Autonomy inside a fence <span className="text-[#8ea4f0]">you draw.</span>
            </>
          }
          lede="Five sensitive action categories — purchases, deposits, emails, contracts, private data — each with an Auto or Ask-first toggle, plus a dollar limit that bypasses approval. Every proposed action passes four ordered checks."
        />

        <div className="mt-14 grid gap-10 lg:grid-cols-[1.15fr_1fr]">
          {/* ordered decision flow */}
          <div className="space-y-3" data-reveal>
            {GATE_CHECKS.map((row, i) => (
              <div
                key={row.n}
                className="lp-gate-row relative flex items-start gap-4 rounded-[12px] border border-white/10 bg-white/[0.03] px-5 py-4"
                style={{ "--gd": `${i * 2.4}s` } as CSSProperties}
              >
                <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border border-white/20 font-mono text-[12px] font-bold text-[#aebffb]">
                  {row.n}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[14.5px] font-semibold text-[#eef1f7]">{row.check}</p>
                  <p className="mt-1 text-[13px] leading-[1.6] text-[#a7b2cc]">{row.detail}</p>
                </div>
                <span
                  className={`chip mt-0.5 shrink-0 ${
                    row.tone === "green" ? "bg-positive/15 text-[#8fdba0]" : "bg-warn/15 text-[#f2c47e]"
                  }`}
                >
                  {row.outcome}
                </span>
                {i < GATE_CHECKS.length - 1 && (
                  <span className="absolute left-[33px] top-full h-3 w-px bg-white/15" aria-hidden />
                )}
              </div>
            ))}

            <div className="mt-5 rounded-[12px] border border-warn/30 bg-warn/[0.07] px-5 py-4" data-reveal>
              <p className="font-mono text-[11px] tracking-[0.1em] text-[#f2c47e] uppercase">Worked example</p>
              <p className="mt-2 text-[13.5px] leading-[1.65] text-[#cbd4e8]">
                A $2,940 tote order against a $500 auto-approve limit isn't blocked or silently executed — it lands on
                your dashboard with an amber <span className="font-semibold text-[#f2c47e]">Over limit</span> flag and
                the exact reason: “$2,940 exceeds your $500 auto-approve limit.”
              </p>
            </div>
          </div>

          {/* safety guarantees */}
          <div className="grid gap-4 content-start">
            {SAFETY_CARDS.map((card, i) => (
              <div
                key={card.title}
                className="rounded-[12px] border border-white/10 bg-white/[0.04] p-5 transition-colors hover:border-white/25"
                data-reveal
                style={{ "--rd": `${i * 80}ms` } as CSSProperties}
              >
                <h3 className="text-[15px] font-semibold text-[#eef1f7]">{card.title}</h3>
                <p className="mt-2 text-[13px] leading-[1.65] text-[#a7b2cc]">{card.body}</p>
              </div>
            ))}
            <p className="px-1 font-mono text-[11px] leading-[1.7] tracking-[0.04em] text-[#8fa0c4]" data-reveal>
              policy allow-list: lu.ma · partiful.com · eventbrite.com · meetup.com · mail.google.com ·
              calendar.google.com
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function DemoSection() {
  return (
    <section id="demo" tabIndex={-1} className="scroll-mt-28 py-24 outline-none lg:scroll-mt-20">
      <div className={CONTAINER}>
        <SectionHeading
          eyebrow="The demo"
          title={
            <>
              Watch a <span className="text-brand">real run.</span>
            </>
          }
          lede="A full pass through the product — brief to plan, an approval resolving on the live dashboard, and an Agent View replay of the browser doing the actual work."
        />

        {/* video placeholder — swap for the real embed later */}
        <div className="relative mt-12 overflow-hidden rounded-[18px] border border-line shadow-modal" data-reveal>
          <div className="lp-video-bg relative aspect-video w-full">
            <div className="absolute inset-0 grid place-items-center">
              <div className="text-center">
                {/* decorative play glyph — a real button would be an inert tab stop */}
                <div
                  aria-hidden="true"
                  className="relative mx-auto grid size-[76px] place-items-center rounded-full bg-white/95 shadow-modal"
                >
                  <span className="lp-ping absolute inset-0 rounded-full border-2 border-white/60" />
                  <span className="lp-ping-late absolute inset-0 rounded-full border border-white/40" />
                  <span className="ml-1 inline-block border-y-[13px] border-l-[21px] border-y-transparent border-l-ink" />
                </div>
                <p className="mt-6 font-mono text-[11px] font-semibold tracking-[0.22em] text-[#8fa0c4] uppercase">
                  Demo video — coming soon
                </p>
              </div>
            </div>
            {/* fake player chrome */}
            <div
              aria-hidden="true"
              className="absolute inset-x-0 bottom-0 flex items-center gap-3 border-t border-white/10 bg-[#10182b]/80 px-5 py-3 backdrop-blur-sm"
            >
              <span className="inline-block border-y-[6px] border-l-[10px] border-y-transparent border-l-white/80" />
              <div className="lp-shimmer h-1 flex-1 rounded-full bg-white/15" />
              <span className="font-mono text-[10.5px] text-white/60">0:00 / --:--</span>
            </div>
          </div>
        </div>

        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          {[
            "A brief becomes a plan — timeline, budget, risks, backups.",
            "An over-limit purchase pauses, gets approved, proceeds.",
            "The Agent View replay: a cloud browser, click by click.",
          ].map((caption, i) => (
            <p key={caption} className="flex items-start gap-2.5 text-[13px] leading-[1.6] text-ink-soft" data-reveal style={{ "--rd": `${i * 80}ms` } as CSSProperties}>
              <span className="mt-1 font-mono text-[11px] font-bold text-brand">{String(i + 1).padStart(2, "0")}</span>
              {caption}
            </p>
          ))}
        </div>
      </div>
    </section>
  );
}

function AboutSection() {
  return (
    <section id="about" tabIndex={-1} className="scroll-mt-28 border-t border-line bg-surface/50 py-24 outline-none lg:scroll-mt-20">
      <div className={CONTAINER}>
        <div className="grid gap-12 lg:grid-cols-[1fr_1.1fr]">
          <SectionHeading
            eyebrow="The build"
            title={
              <>
                Built in a day, <span className="text-brand">honestly.</span>
              </>
            }
            lede="Occasion is a solo build by Amresh Balakrishnan for the July 11 San Francisco hackathon. Everything this page claims is in the codebase today — and what isn't real yet is labeled roadmap, not feature."
          />

          <div data-reveal style={{ "--rd": "120ms" } as CSSProperties}>
            <div className="card divide-y divide-line">
              {STACK_ROWS.map((row) => (
                <div key={row.k} className="flex gap-5 px-6 py-4">
                  <span className="w-[72px] shrink-0 pt-0.5 font-mono text-[11px] font-bold tracking-[0.12em] text-brand uppercase">
                    {row.k}
                  </span>
                  <span className="text-[13.5px] leading-[1.6] text-ink-soft">{row.v}</span>
                </div>
              ))}
            </div>
            <p className="mt-5 text-[13px] leading-[1.65] text-ink-soft">
              Next in line: day-of supervision and a Gradium voice interface — both scaffolded in the codebase and
              deliberately unclaimed here until they're real.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function CtaBand() {
  return (
    <section className="relative overflow-hidden bg-ink py-24 text-center text-white">
      <div className="lp-blob pointer-events-none absolute -top-32 left-1/2 size-[480px] -translate-x-1/2 rounded-full bg-brand/20 blur-3xl" aria-hidden />
      <div className={`${CONTAINER} relative`} data-reveal>
        <p className="eyebrow !text-[#8fa0c4]">Try Occasion</p>
        <h2 className="mx-auto mt-4 max-w-[640px] font-serif text-[clamp(34px,5vw,56px)] leading-[1.05] font-medium tracking-[-0.015em]">
          Stop coordinating. <span className="text-[#8ea4f0]">Start approving.</span>
        </h2>
        <p className="mx-auto mt-5 max-w-[520px] text-[15px] leading-[1.65] text-[#a7b2cc]">
          Tell Occasion what you&apos;re planning. It spins up the project, drafts the plan, and puts its agents to work
          on real websites — pausing for your sign-off before anything binding.
        </p>
        <Link href="/ask?new=1" className="btn btn-primary mt-8 inline-block px-7 py-3 text-[15px]">
          Open the dashboard →
        </Link>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-line bg-canvas py-8">
      <div className={`${CONTAINER} flex flex-wrap items-center justify-between gap-4`}>
        <p className="font-serif text-[18px] font-medium">Occasion</p>
        <p className="font-mono text-[11px] tracking-[0.08em] text-ink-soft">
          autonomous event operations · built for the 7/11 SF hackathon
        </p>
        <Link href="/ask?new=1" className="text-[13px] font-semibold text-brand hover:underline">
          Dashboard →
        </Link>
      </div>
    </footer>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function LandingPage() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [animate, setAnimate] = useState(false);

  // SMIL diagram dots only run when the visitor hasn't asked for reduced motion.
  useEffect(() => {
    setAnimate(!prefersReducedMotion());
  }, []);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    // The pre-reveal hidden state is scoped to `.lp.js`, so content stays
    // visible for no-JS visitors and pre-hydration paints.
    root.classList.add("js");
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            io.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -6% 0px" },
    );
    root.querySelectorAll("[data-reveal]").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <div ref={rootRef} className="lp bg-canvas text-[15px] leading-[1.6] text-ink">
      <style>{PAGE_CSS}</style>
      <Nav />
      <main>
        <ProductSection />
        <HowSection animate={animate} />
        <CapabilitiesSection />
        <SafetySection />
        <DemoSection />
        <AboutSection />
        <CtaBand />
      </main>
      <Footer />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Animation CSS — scoped under .lp; keyframes carry an lp- prefix     */
/* ------------------------------------------------------------------ */

const PAGE_CSS = `
html { scroll-behavior: smooth; }

/* Reveal is animation-driven (not a transition) so it can't collide with
   hover transitions like lp-lift on the same element. Hidden state only
   applies once JS marks the root, keeping no-JS paints visible. */
.lp.js [data-reveal] { opacity: 0; transform: translateY(18px); }
.lp.js [data-reveal].is-in {
  opacity: 1;
  transform: none;
  animation: lp-reveal-kf 0.7s cubic-bezier(0.16, 1, 0.3, 1) var(--rd, 0ms) backwards;
}
@keyframes lp-reveal-kf {
  from { opacity: 0; transform: translateY(18px); }
}

.lp .lp-lift { transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.35s, border-color 0.35s; }
.lp .lp-lift:hover {
  transform: translateY(-4px);
  border-color: var(--color-brand-mist);
  box-shadow: 0 2px 4px rgba(23, 32, 58, 0.05), 0 14px 34px rgba(23, 32, 58, 0.1);
}

.lp .lp-dotgrid {
  background-image: radial-gradient(var(--color-line-strong) 1px, transparent 1px);
  background-size: 24px 24px;
  mask-image: radial-gradient(ellipse 75% 65% at 50% 30%, black 30%, transparent 75%);
  -webkit-mask-image: radial-gradient(ellipse 75% 65% at 50% 30%, black 30%, transparent 75%);
  opacity: 0.6;
}

@keyframes lp-caret-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
.lp .lp-caret { animation: lp-caret-blink 0.9s step-end infinite; }

@keyframes lp-pulse-kf { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
.lp .lp-pulse { animation: lp-pulse-kf 1.6s ease-in-out infinite; }

@keyframes lp-ping-kf {
  0% { transform: scale(0.75); opacity: 0.9; }
  100% { transform: scale(1.9); opacity: 0; }
}
.lp .lp-ping { animation: lp-ping-kf 2.6s cubic-bezier(0, 0, 0.2, 1) infinite; }
.lp .lp-ping-late { animation: lp-ping-kf 2.6s cubic-bezier(0, 0, 0.2, 1) 1.3s infinite; }

@keyframes lp-stamp-kf {
  0% { transform: scale(1.7) rotate(-14deg); opacity: 0; }
  60% { transform: scale(0.94) rotate(-8deg); opacity: 1; }
  100% { transform: scale(1) rotate(-8deg); opacity: 1; }
}
.lp .lp-stamp { animation: lp-stamp-kf 0.45s cubic-bezier(0.16, 1, 0.3, 1) both; }

@keyframes lp-march-kf { to { stroke-dashoffset: -32; } }
.lp .lp-march { animation: lp-march-kf 1.4s linear infinite; }

@keyframes lp-marquee-kf { to { transform: translateX(-50%); } }
.lp .lp-marquee { animation: lp-marquee-kf 34s linear infinite; }
.lp .lp-marquee:hover { animation-play-state: paused; }
.lp .lp-marquee-mask {
  overflow: hidden;
  mask-image: linear-gradient(to right, transparent, black 12%, black 88%, transparent);
  -webkit-mask-image: linear-gradient(to right, transparent, black 12%, black 88%, transparent);
}

@keyframes lp-blob-kf { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-22px); } }
.lp .lp-blob { animation: lp-blob-kf 9s ease-in-out infinite; }
.lp .lp-blob-slow { animation: lp-blob-kf 13s ease-in-out 1.5s infinite; }

/* Orbiting fleet chips: rotate around the hub while staying upright. */
@keyframes lp-orbit-cw-kf {
  from { transform: rotate(var(--a)) translateX(var(--r)) rotate(calc(var(--a) * -1)) translate(-50%, -50%); }
  to { transform: rotate(calc(var(--a) + 360deg)) translateX(var(--r)) rotate(calc((var(--a) + 360deg) * -1)) translate(-50%, -50%); }
}
@keyframes lp-orbit-ccw-kf {
  from { transform: rotate(var(--a)) translateX(var(--r)) rotate(calc(var(--a) * -1)) translate(-50%, -50%); }
  to { transform: rotate(calc(var(--a) - 360deg)) translateX(var(--r)) rotate(calc((var(--a) - 360deg) * -1)) translate(-50%, -50%); }
}
.lp .lp-orbit-cw {
  transform: rotate(var(--a)) translateX(var(--r)) rotate(calc(var(--a) * -1)) translate(-50%, -50%);
  animation: lp-orbit-cw-kf 46s linear infinite;
}
.lp .lp-orbit-ccw {
  transform: rotate(var(--a)) translateX(var(--r)) rotate(calc(var(--a) * -1)) translate(-50%, -50%);
  animation: lp-orbit-ccw-kf 32s linear infinite;
}

/* Gate rows take turns lighting up, walking the decision in order. */
@keyframes lp-gate-kf {
  0%, 20%, 100% { background-color: rgba(255, 255, 255, 0.03); border-color: rgba(255, 255, 255, 0.1); }
  6%, 14% { background-color: rgba(94, 122, 224, 0.12); border-color: rgba(142, 164, 240, 0.45); }
}
.lp .lp-gate-row { animation: lp-gate-kf 9.6s ease-in-out var(--gd, 0s) infinite; }

.lp .lp-video-bg {
  background:
    radial-gradient(ellipse 60% 55% at 50% 42%, rgba(59, 91, 219, 0.16), transparent 70%),
    linear-gradient(160deg, #131a2c, #1c2438 55%, #131a2c);
}

@keyframes lp-shimmer-kf { to { background-position: 200% 0; } }
.lp .lp-shimmer {
  background-image: linear-gradient(90deg, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0.45) 40%, rgba(255,255,255,0.15) 80%);
  background-size: 200% 100%;
  animation: lp-shimmer-kf 2.8s linear infinite;
}

.lp .lp-arrow { animation: lp-pulse-kf 2.4s ease-in-out infinite; }

/* Page-local contrast bumps: the shared chip tokens sit just under AA at 10.5px. */
.lp .chip-amber { color: #8a5200; }
.lp .chip-green { color: #1f6b31; }

/* The global brand outline is invisible on the dark bands. */
.lp .bg-ink :focus-visible,
.lp #safety :focus-visible {
  outline-color: #aebffb;
}

@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  .lp *, .lp *::before, .lp *::after {
    animation-duration: 0.01ms !important;
    animation-delay: 0ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
  .lp.js [data-reveal] { opacity: 1; transform: none; animation: none !important; }
}
`;
