"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ChatPanel, type RequirementsData } from "@/components/ChatPanel";
import { createEvent, DEFAULT_EVENT_ID, EVENT_COOKIE, sendChatMessage, updateEventDetails } from "@/lib/api";

const EXIT_MS = 650; // covers the 600ms fade below with a little margin

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** The active event, read client-side; the cookie is not httpOnly by design. */
function readEventCookie(): string {
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${EVENT_COOKIE}=`));
  return match ? decodeURIComponent(match.slice(EVENT_COOKIE.length + 1)) : DEFAULT_EVENT_ID;
}

/** Make an event the active project the dashboard's server pages read. */
function setActiveEvent(eventId: string) {
  document.cookie = `${EVENT_COOKIE}=${encodeURIComponent(eventId)}; path=/; max-age=31536000`;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** The event's editable descriptors, drawn from what the interview captured. */
function eventPatch(requirements: RequirementsData) {
  const patch: { name?: string; kind?: string; date?: string; location?: string; headcount?: string } = {};
  const name = deriveName(requirements);
  if (name) patch.name = name;
  if (requirements.event_type) patch.kind = requirements.event_type;
  if (requirements.date) patch.date = requirements.date;
  if (requirements.location) patch.location = requirements.location;
  if (requirements.headcount != null) patch.headcount = `${requirements.headcount} guests`;
  return patch;
}

/**
 * The brief the completed interview hands to the sourcing workflow. The JSON body
 * carries every captured field verbatim, so the workflow re-derives the requirements
 * without needing the chat transcript.
 */
function kickoffBrief(requirements: RequirementsData): string {
  return [
    "Plan this event end-to-end and research vendors for every category it needs.",
    `Captured event brief (JSON): ${JSON.stringify(requirements)}`,
  ].join("\n");
}

/** A readable project title; the interview captures an event type and place, never a name. */
function deriveName(requirements: RequirementsData): string | null {
  const type = requirements.event_type?.trim();
  if (!type) return null;
  const titled = type.charAt(0).toUpperCase() + type.slice(1);
  return requirements.location ? `${titled} · ${requirements.location}` : titled;
}

/**
 * The intake funnel the landing CTAs open: one big question over a living
 * gradient. Arriving with `?new=1` provisions a fresh project so the interview —
 * and its chat thread, keyed by event id — starts blank. ChatPanel runs the
 * requirements interview here and calls back when the brief is complete, at which
 * point the captured brief is saved onto the event and the content dissolves into
 * the dashboard.
 */
export default function AskPage() {
  const router = useRouter();
  const [eventId, setEventId] = useState<string | null>(null);
  const [exiting, setExiting] = useState(false);
  const startedRef = useRef(false); // provision the fresh project at most once

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    router.prefetch("/dashboard/ask"); // the intake handoff should land instantly

    const startFresh = new URLSearchParams(window.location.search).get("new") === "1";
    if (!startFresh) {
      setEventId(readEventCookie());
      return;
    }
    // A "start a new project" CTA: spin up a blank event and make it active. Drop the
    // flag afterward so a reload mid-interview resumes this project instead of spawning another.
    createEvent()
      .then((event) => {
        setActiveEvent(event.id);
        setEventId(event.id);
        window.history.replaceState(null, "", "/ask");
      })
      .catch(() => {
        // Agent service unreachable: fall back to the active event so the page still runs;
        // ChatPanel surfaces the outage on the first turn.
        setEventId(readEventCookie());
      });
  }, [router]);

  function finish(requirements: RequirementsData) {
    // Save what the interview captured so the new project opens named and populated,
    // not as the neutral placeholder it was created with.
    const patch = eventPatch(requirements);
    const persisted =
      eventId && Object.keys(patch).length > 0
        ? updateEventDetails(eventId, patch).catch(() => undefined)
        : Promise.resolve(undefined);
    // The agents' real work starts here: one background sourcing run that plans the
    // event and fans out browser research sessions — the ones the dashboard's
    // "Agents at work" rail streams. The POST only creates the run; it executes
    // server-side, so navigating away doesn't lose it.
    const kickoff = eventId
      ? sendChatMessage(kickoffBrief(requirements), eventId, "workflow/vendor_sourcing").catch(() => undefined)
      : Promise.resolve(undefined);

    if (prefersReducedMotion()) {
      void Promise.all([persisted, kickoff]).finally(() => router.push("/dashboard/ask"));
      return;
    }
    setExiting(true);
    // Let the save, the kickoff, and the exit fade run together; hand off once all settle.
    void Promise.all([persisted, kickoff, delay(EXIT_MS)]).finally(() => router.push("/dashboard/ask"));
  }

  return (
    <div className={`ask relative flex min-h-screen flex-col overflow-hidden ${exiting ? "ask-exit" : ""}`}>
      <style>{ASK_CSS}</style>
      <div className="ask-bg" aria-hidden="true" />
      <div className="ask-blob ask-blob-a" aria-hidden="true" />
      <div className="ask-blob ask-blob-b" aria-hidden="true" />

      {/* Header sits outside the fade so the escape hatch survives the exit. */}
      <header className="relative z-10 flex items-center justify-between px-6 py-5 md:px-10">
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
          Skip to dashboard →
        </Link>
      </header>

      <main className="ask-fade relative z-10 mx-auto flex w-full max-w-[760px] flex-1 flex-col justify-center gap-7 px-6 pb-16">
        <div className="text-center">
          <h1 className="font-serif text-[clamp(40px,7vw,64px)] leading-[1.05] font-medium tracking-[-0.02em]">
            What's the occasion?
          </h1>
          <p className="mx-auto mt-3 max-w-[52ch] text-[15px] leading-relaxed text-ink-soft">
            Describe the event you're planning. Occasion interviews you for the brief, then its
            agents get to work on real websites.
          </p>
        </div>
        {eventId && <ChatPanel eventId={eventId} mode="intake" onIntakeComplete={finish} />}
      </main>
    </div>
  );
}

const ASK_CSS = `
.ask { background: #ffffff; }
.ask-bg {
  position: absolute; inset: 0; pointer-events: none;
  background:
    radial-gradient(ellipse 90% 55% at 50% -12%, rgba(59, 91, 219, 0.40), transparent 62%),
    radial-gradient(ellipse 110% 60% at 50% 114%, rgba(214, 64, 94, 0.28), transparent 64%),
    linear-gradient(180deg, #dfe7fb 0%, #ffffff 46%, #ffe6ec 100%);
}
.ask-blob { position: absolute; border-radius: 9999px; filter: blur(80px); opacity: 0.5; pointer-events: none; }
.ask-blob-a {
  width: 520px; height: 520px; top: -160px; left: -140px; background: #8ea4f0;
  animation: ask-drift-a 18s ease-in-out infinite alternate;
}
.ask-blob-b {
  width: 560px; height: 560px; bottom: -200px; right: -160px; background: #f4a7bb;
  animation: ask-drift-b 23s ease-in-out infinite alternate;
}
@keyframes ask-drift-a { to { transform: translate(60px, 44px) scale(1.08); } }
@keyframes ask-drift-b { to { transform: translate(-70px, -50px) scale(1.06); } }
.ask-fade {
  transition: opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1), transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
.ask-exit .ask-fade { opacity: 0; transform: translateY(-16px) scale(0.985); }
@media (prefers-reduced-motion: reduce) {
  .ask *, .ask *::before, .ask *::after { animation: none !important; transition-duration: 0.01ms !important; }
}
`;
