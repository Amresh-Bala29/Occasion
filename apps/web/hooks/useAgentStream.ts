"use client";

import { useEffect, useRef, useState } from "react";

import { getAgentSessions, getSessionHealth } from "@/lib/api";
import type { EventSessionsReport, SessionHealth } from "@/types";

const FETCH_MS = 5_000;
// The live grid's canonical view is a 2x2 of four browsers; step-checking more rows
// than that is wasted round-trips even on bigger plans.
const HEALTH_LIMIT = 4;

// Statuses that mean "still doing work". The agent-sessions endpoint also returns
// `idle` (a settled one-shot run still pinning its slot) — no point stepping those.
const PROGRESSING = new Set(["queued", "pending", "starting", "running", "paused", "awaiting_tool_results"]);

export interface AgentStreamState {
  report: EventSessionsReport | null;
  health: Record<string, SessionHealth>;
}

/** True while this session is worth watching for progress. */
export function isProgressing(status: string): boolean {
  return PROGRESSING.has(status);
}

/**
 * Live signals behind the chat's working surfaces — the thinking bubble and the
 * live browser grid: the event's H sessions, fast-polled, plus each live one's
 * step counter. H exposes no push surface, so this polls — a failed tick keeps
 * the last good state.
 */
export function useAgentStream(eventId: string, enabled: boolean): AgentStreamState {
  const [report, setReport] = useState<EventSessionsReport | null>(null);
  const [health, setHealth] = useState<Record<string, SessionHealth>>({});
  const inFlight = useRef(false);

  useEffect(() => {
    if (!enabled) {
      setReport(null);
      setHealth({});
      return;
    }
    let cancelled = false;

    const tick = async () => {
      if (inFlight.current) return; // H can be slow; never stack polls
      inFlight.current = true;
      try {
        const next = await getAgentSessions(eventId);
        if (cancelled) return;
        setReport(next);
        if (!next.succeeded) return; // H unreachable or unconfigured: nothing to step-check
        const live = next.sessions.filter((session) => isProgressing(session.status)).slice(0, HEALTH_LIMIT);
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
        // Keep the last good report; a blip should not blank the ticker.
      } finally {
        inFlight.current = false;
      }
    };

    void tick();
    const poller = setInterval(() => void tick(), FETCH_MS);
    return () => {
      cancelled = true;
      clearInterval(poller);
    };
  }, [eventId, enabled]);

  return { report, health };
}
