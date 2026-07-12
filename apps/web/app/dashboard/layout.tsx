import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { AgentPanel } from "@/components/AgentPanel";
import { Sidebar } from "@/components/Sidebar";
import { EventProvider } from "@/hooks/useEvent";
import { DEFAULT_EVENT_ID, EVENT_COOKIE, getDashboardData, getDecisionHistory, getEvents, getSpendingRules } from "@/lib/api";

// The dashboard renders live per-request event data from the agent service, so it
// must never be statically prerendered at build time (the backend isn't up then).
// Set on the shared layout so every nested dashboard route inherits it.
export const dynamic = "force-dynamic";

/** Shared shell for all event pages: sidebar, main column, and the live agent rail. */
export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const eventId = (await cookies()).get(EVENT_COOKIE)?.value ?? DEFAULT_EVENT_ID;
  const [data, decisions, rules, events] = await Promise.all([
    getDashboardData(eventId),
    getDecisionHistory(eventId),
    getSpendingRules(eventId),
    getEvents(),
  ]);

  return (
    // Keyed by event so switching remounts the provider — client state (approvals,
    // activity, rules) re-seeds from the new event instead of surviving the switch.
    <EventProvider
      key={eventId}
      initial={{
        eventId,
        approvals: data.approvals,
        decisions,
        activity: data.activity,
        autoApproveLimit: data.autoApproveLimit,
        rules,
      }}
    >
      <div className="grid min-h-screen grid-cols-1 md:grid-cols-[248px_minmax(0,1fr)] xl:grid-cols-[248px_minmax(0,1fr)_clamp(340px,26vw,408px)]">
        <Sidebar
          activeEvent={data.event.shortName}
          activeEventId={eventId}
          events={events}
          messagesCount={data.messagesCount}
        />
        <div className="flex min-w-0 flex-col md:col-start-2 md:row-start-1">{children}</div>
        <AgentPanel agents={data.agents} />
      </div>
    </EventProvider>
  );
}
