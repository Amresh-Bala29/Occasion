import type { ReactNode } from "react";

import { AgentPanel } from "@/components/AgentPanel";
import { Sidebar } from "@/components/Sidebar";
import { EventProvider } from "@/hooks/useEvent";
import { getActivityPool, getDashboardData, getDecisionHistory, getSpendingRules } from "@/lib/api";

/** Shared shell for all event pages: sidebar, main column, and the live agent rail. */
export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const [data, decisions, rules, activityPool] = await Promise.all([
    getDashboardData(),
    getDecisionHistory(),
    getSpendingRules(),
    getActivityPool(),
  ]);

  return (
    <EventProvider
      initial={{
        approvals: data.approvals,
        decisions,
        activity: data.activity,
        autoApproveLimit: data.autoApproveLimit,
        rules,
        activityPool,
      }}
    >
      <div className="grid min-h-screen grid-cols-1 md:grid-cols-[248px_minmax(0,1fr)] xl:grid-cols-[248px_minmax(0,1fr)_clamp(340px,26vw,408px)]">
        <Sidebar activeEvent={data.event.shortName} messagesCount={data.messagesCount} />
        <div className="flex min-w-0 flex-col md:col-start-2 md:row-start-1">{children}</div>
        <AgentPanel agents={data.agents} />
      </div>
    </EventProvider>
  );
}
