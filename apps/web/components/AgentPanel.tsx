"use client";

import { useEffect, useRef, useState } from "react";

import { isProgressing } from "@/hooks/useAgentStream";
import { useEvent } from "@/hooks/useEvent";
import { getAgentSessions, getSessionHealth } from "@/lib/api";
import type {
  ActivityItem,
  AgentStatus,
  EventSessionsReport,
  ObstaclesSummary,
  SessionHealth,
  Tone,
} from "@/types";

// H's platform refuses framing today (verified 2026-07-12: platform.hcompany.ai
// sends X-Frame-Options: DENY and CSP frame-ancestors 'none', plus a login wall),
// so embedded live previews cannot render. Flip to true if H ever allows it —
// the first LIVE_EMBED_LIMIT sessions then show scaled live views inline.
const EMBED_LIVE_VIEW = false;
const LIVE_EMBED_LIMIT = 2; // more concurrent iframes than this chokes the rail

interface AgentPanelProps {
  agents: AgentStatus[];
  // The hardcoded demo events drop the static agent list so Live Browsers leads the rail.
  demo?: boolean;
}

const SESSIONS_POLL_MS = 15_000;

// Free-tier H accounts have 3 session slots; health-checking more rows than that
// is wasted round-trips even on bigger plans.
const HEALTH_LIMIT = 3;

// Terminal states keep their card: H's live view is blank mid-run, so the replay
// page a finished session leaves behind is where its work is actually visible.
const TERMINAL_STATUSES = new Set(["completed", "failed", "timed_out", "interrupted"]);

// Demo only: the fixture's activity is pre-seeded, so it would otherwise render fully
// formed. Instead it streams in once the browsers go live — the first detected session is
// the reference point (actual browser-start is not observable) — so the rail reads as work
// happening, not a static list.
const ACTIVITY_STREAM_DELAY_MS = 10_000; // first line lands 10s after the first live session
const ACTIVITY_STREAM_STEP_MS = 2_500; // then one more line every 2.5s

const RING_BY_TONE: Record<Tone, string> = {
  green: "border-positive",
  blue: "border-brand",
  amber: "border-warn",
  gray: "border-ink-mist",
};

const FILL_BY_TONE: Record<Tone, string> = {
  green: "bg-positive",
  blue: "bg-brand",
  amber: "bg-warn",
  gray: "bg-ink-mist",
};

const NAME_BY_TONE: Record<Tone, string> = {
  green: "text-positive-deep",
  amber: "text-warn-deep",
  blue: "",
  gray: "",
};

/** Right-hand rail: live per-agent status plus the recent activity feed. */
export function AgentPanel({ agents, demo = false }: AgentPanelProps) {
  const { eventId, activity } = useEvent();
  const [sessionsReport, setSessionsReport] = useState<EventSessionsReport | null>(null);
  const [health, setHealth] = useState<Record<string, SessionHealth>>({});
  const inFlight = useRef(false);
  // Demo streaming: the moment the browsers first go live, and a 1s clock to advance the reveal.
  const [browsersStartedAt, setBrowsersStartedAt] = useState<number | null>(null);
  const [clockMs, setClockMs] = useState(0);

  // Poll the live H sessions, then step-check the few in-flight ones; a failed
  // poll keeps the last good report so the rail never breaks when the agent
  // service or H is unreachable.
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (inFlight.current) return; // H can be slow; never stack polls
      inFlight.current = true;
      try {
        const report = await getAgentSessions(eventId);
        if (cancelled) return;
        setSessionsReport(report);
        if (!report.succeeded) return; // H unreachable or unconfigured: nothing to step-check
        const live = report.sessions.filter((session) => isProgressing(session.status)).slice(0, HEALTH_LIMIT);
        const checks = await Promise.all(
          live.map((session) => getSessionHealth(eventId, session.id).catch(() => null)),
        );
        if (cancelled) return;
        // Merge instead of replace so a single failed check never blanks a counter.
        setHealth((previous) => {
          const merged = { ...previous };
          for (const check of checks) {
            if (check) merged[check.session_id] = check;
          }
          return merged;
        });
      } catch {
        // Keep the last good report; a blip should not blank the rail.
      } finally {
        inFlight.current = false;
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), SESSIONS_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [eventId]);

  // Mark when the browsers first go live — the reference point the demo activity stream counts from.
  useEffect(() => {
    if (!demo || browsersStartedAt !== null) return;
    if (sessionsReport?.succeeded && sessionsReport.sessions.some((session) => isProgressing(session.status))) {
      setBrowsersStartedAt(Date.now());
    }
  }, [demo, browsersStartedAt, sessionsReport]);

  // Tick once a second while the reveal is in progress so elapsed time advances the feed.
  useEffect(() => {
    if (!demo || browsersStartedAt === null) return;
    const tick = () => setClockMs(Date.now());
    tick();
    const timer = setInterval(tick, 1_000);
    return () => clearInterval(timer);
  }, [demo, browsersStartedAt]);

  const visibleActivity = streamedActivity(activity, demo, browsersStartedAt, clockMs);

  return (
    <aside
      className="border-t border-line bg-surface px-[22px] pt-5 pb-7 md:col-start-2 xl:sticky xl:top-0 xl:col-start-3 xl:row-start-1 xl:h-screen xl:overflow-y-auto xl:border-t-0 xl:border-l"
      aria-label="Agents at work"
    >
      <div className="flex items-center justify-between gap-2.5">
        <h2 className="text-[15.5px] font-bold">Agents at work</h2>
        <span className="inline-flex items-center gap-1.5 font-mono text-[10.5px] font-bold tracking-[0.12em] text-positive-deep uppercase">
          <span className="dot dot-green animate-pulse" aria-hidden="true" />
          Live
        </span>
      </div>
      <p
        className={`mt-[7px] pb-3.5 text-[12.5px] leading-normal text-ink-soft${
          demo ? "" : " border-b border-line"
        }`}
      >
        Every action your team takes on real vendor sites, in real time.
      </p>

      {/* The hardcoded demo events skip the static roster so Live Browsers leads the rail. */}
      {!demo && (
        <ul className="pt-2.5 pb-1.5">
          {agents.map((agent) => (
            <li key={agent.name} className="flex items-center gap-2.5 py-[7px]">
              <span className={`dot dot-${agent.tone}`} aria-hidden="true" />
              <span className="w-[104px] shrink-0 text-[13.5px] font-semibold">{agent.name}</span>
              <span className="flex-1 font-mono text-[11px] leading-[1.4] text-ink-soft">{agent.status}</span>
            </li>
          ))}
        </ul>
      )}

      <LiveSessions report={sessionsReport} health={health} />

      <ObstaclesCleared obstacles={sessionsReport?.succeeded ? sessionsReport.obstacles : null} />

      {/* Non-demo shows the whole feed; a demo holds it until items start streaming in. */}
      {(!demo || visibleActivity.length > 0) && (
        <div className="mt-2 border-t border-line pt-4">
          <h3 className="eyebrow">Activity</h3>
          <ul className="mt-3.5 flex flex-col gap-[18px]">
            {visibleActivity.map((item) => (
              <li
                key={item.id}
                className={`flex gap-2.5${demo ? " transition-opacity duration-500 starting:opacity-0" : ""}`}
              >
                <span
                  className={`relative mt-0.5 size-[15px] shrink-0 rounded-full border-[1.5px] ${RING_BY_TONE[item.tone]}`}
                  aria-hidden="true"
                >
                  <span className={`absolute inset-[3.5px] rounded-full ${FILL_BY_TONE[item.tone]}`} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2.5">
                    <span className={`text-[12.5px] font-semibold ${NAME_BY_TONE[item.tone]}`}>
                      {item.agent}
                    </span>
                    <span className="font-mono text-[10.5px] whitespace-nowrap text-ink-faint">
                      {item.timeAgo}
                    </span>
                  </div>
                  <p className="mt-[3px] text-[12.5px] leading-normal text-ink-soft">{item.description}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}

/** Demo only: reveal the pre-seeded feed oldest-first, starting `ACTIVITY_STREAM_DELAY_MS`
 * after the browsers go live, so newer lines stream in at the top. Non-demo rails show the
 * whole feed at once, and nothing shows until the browsers start. */
function streamedActivity(
  activity: ActivityItem[],
  demo: boolean,
  browsersStartedAt: number | null,
  clockMs: number,
): ActivityItem[] {
  if (!demo) return activity;
  if (browsersStartedAt === null) return [];
  const elapsed = clockMs - browsersStartedAt;
  if (elapsed < ACTIVITY_STREAM_DELAY_MS) return [];
  const revealed = Math.min(
    activity.length,
    1 + Math.floor((elapsed - ACTIVITY_STREAM_DELAY_MS) / ACTIVITY_STREAM_STEP_MS),
  );
  return activity.slice(activity.length - revealed); // tail = oldest; newer lines arrive on top
}

// The strip stays scannable; the durable trail lives in the Activity feed below.
const OBSTACLE_LINE_LIMIT = 4;

/** The messy-web scoreboard: cookie walls, popups, and lists the sessions worked through. */
function ObstaclesCleared({ obstacles }: { obstacles?: ObstaclesSummary | null }) {
  if (!obstacles || obstacles.cleared_total === 0) return null;
  return (
    <div className="mt-2 border-t border-line pt-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="eyebrow">Obstacles cleared</h3>
        <span className="rounded-full bg-positive-soft px-2 py-0.5 font-mono text-[10.5px] font-bold text-positive-deep">
          ✓ {obstacles.cleared_total}
        </span>
      </div>
      <ul className="mt-3 flex flex-col gap-2">
        {obstacles.lines.slice(0, OBSTACLE_LINE_LIMIT).map((line, index) => (
          <li key={`${line.session_id}-${line.at ?? index}`} className="flex items-baseline gap-2">
            <span className="shrink-0 text-[12px] font-bold text-positive-deep" aria-hidden="true">
              ✓
            </span>
            <span className="line-clamp-1 min-w-0 flex-1 text-[12px] text-ink-soft">{line.label}</span>
            {line.agent && (
              <span className="shrink-0 font-mono text-[10px] text-ink-faint">
                {line.agent.replace(/^occasion-/, "")}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Real H browser sessions for the event; absent entirely when H is idle or unconfigured. */
function LiveSessions({
  report,
  health,
}: {
  report: EventSessionsReport | null;
  health: Record<string, SessionHealth>;
}) {
  if (!report?.succeeded || report.sessions.length === 0) return null;

  // Only the first couple of watchable sessions earn an inline preview; the rest
  // stay compact rows so a busy fleet can't fill the rail with iframes.
  const embedIds = new Set(
    EMBED_LIVE_VIEW
      ? report.sessions
          .filter((session) => session.agent_view_url)
          .slice(0, LIVE_EMBED_LIMIT)
          .map((session) => session.id)
      : [],
  );

  return (
    <div className="mt-2 border-t border-line pt-4">
      <h3 className="eyebrow">Live Browsers</h3>
      <ul className="mt-3.5 flex flex-col gap-3.5">
        {report.sessions.map((session) => {
          const steps = health[session.id]?.steps;
          return (
            <li key={session.id} className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-[12.5px] font-semibold">{session.agent ?? "agent"}</span>
                <span className={sessionChipClass(session.status)}>{session.status}</span>
                {isProgressing(session.status) && typeof steps === "number" && (
                  <span className="font-mono text-[11px] whitespace-nowrap text-ink-soft">{steps} steps</span>
                )}
                {session.agent_view_url && (
                  <a
                    className="ml-auto text-[12px] font-semibold whitespace-nowrap text-brand hover:underline"
                    href={session.agent_view_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {/* H's viewer is blank mid-run; once a session finishes it holds the replay. */}
                    {TERMINAL_STATUSES.has(session.status) ? "Replay ↗" : "Open ↗"}
                  </a>
                )}
              </div>
              {session.task && (
                <p className="mt-[3px] line-clamp-2 text-[12px] leading-normal text-ink-soft">{session.task}</p>
              )}
              {embedIds.has(session.id) && session.agent_view_url && (
                <LiveBrowserPreview url={session.agent_view_url} agent={session.agent ?? "agent"} />
              )}
            </li>
          );
        })}
      </ul>
      {report.quota && (
        <p className="mt-3 font-mono text-[10.5px] text-ink-faint">
          {report.quota.active} active · {report.quota.available} of {report.quota.limit} slots free
        </p>
      )}
    </div>
  );
}

/** A live browser scaled into the rail: a 1280×800 (16:10) frame shrunk to fit,
 * inert as a preview — the "Open ↗" link stays the interactive path. */
function LiveBrowserPreview({ url, agent }: { url: string; agent: string }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  // The rail is clamp(340px,26vw,408px) wide: measure the box instead of guessing.
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={boxRef}
      className="relative mt-2 aspect-[16/10] overflow-hidden rounded-[10px] border border-line bg-canvas"
    >
      {width > 0 && (
        <iframe
          src={url}
          title={`Live browser — ${agent}`}
          loading="lazy"
          referrerPolicy="no-referrer"
          aria-hidden="true"
          className="pointer-events-none absolute top-0 left-0 origin-top-left border-0"
          style={{ width: 1280, height: 800, transform: `scale(${width / 1280})` }}
        />
      )}
    </div>
  );
}

function sessionChipClass(status: string): string {
  if (status === "running") return "chip chip-green";
  if (status === "queued" || status === "pending" || status === "starting") return "chip chip-amber";
  if (status === "failed" || status === "timed_out" || status === "error") return "chip chip-red";
  return "chip chip-gray"; // paused | idle | awaiting_tool_results | completed
}
