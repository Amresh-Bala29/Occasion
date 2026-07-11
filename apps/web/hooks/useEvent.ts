"use client";

// Client-side store for the event state that spans panels: pending approvals,
// decision history, the live activity feed, and spending rules. Deciding an
// approval here updates the sidebar badge, overview KPIs, activity rail, and
// approvals page together. Swap the internals for real APIs when they land.
import { createContext, createElement, useContext, useEffect, useState, type ReactNode } from "react";

import { getActivityPool, getDashboardData, getDecisionHistory, getSpendingRules } from "@/lib/api";
import type { ActivityItem, ApprovalItem, DecisionRecord, SpendingRule } from "@/types";

interface EventStore {
  approvals: ApprovalItem[];
  decisions: DecisionRecord[];
  activity: ActivityItem[];
  autoApproveLimit: string;
  rules: SpendingRule[];
  approve: (id: string) => void;
  decline: (id: string) => void;
  setAutoApproveLimit: (limit: string) => void;
  toggleRule: (id: string) => void;
}

const EventContext = createContext<EventStore | null>(null);

const FEED_LIMIT = 8;
const FEED_TICK_MS = 4600;

export function EventProvider({ children }: { children: ReactNode }) {
  const [approvals, setApprovals] = useState(() => getDashboardData().approvals);
  const [decisions, setDecisions] = useState(getDecisionHistory);
  const [activity, setActivity] = useState(() => getDashboardData().activity);
  const [autoApproveLimit, setAutoApproveLimit] = useState(() => getDashboardData().autoApproveLimit);
  const [rules, setRules] = useState(getSpendingRules);

  // Simulated live feed: rotate pre-written agent updates through the rail
  // until the real event stream lands.
  useEffect(() => {
    const pool = getActivityPool();
    let tick = 0;
    const timer = setInterval(() => {
      const next = pool[tick % pool.length];
      tick += 1;
      setActivity((prev) => [{ ...next, id: `${next.id}-${tick}` }, ...prev].slice(0, FEED_LIMIT));
    }, FEED_TICK_MS);
    return () => clearInterval(timer);
  }, []);

  function decide(id: string, approved: boolean) {
    const item = approvals.find((approval) => approval.id === id);
    if (!item) return;
    const agentName = item.agent.replace(/ agent$/i, "");
    const feedLine = approved
      ? `You approved ${item.title} — ${item.amount}. The ${agentName} agent is proceeding now.`
      : `You declined ${item.title}. The ${agentName} agent will source an alternative.`;

    setApprovals((prev) => prev.filter((approval) => approval.id !== id));
    setDecisions((prev) => [
      { id: `decision-${id}`, title: item.title, amount: item.amount, when: "just now", approved },
      ...prev,
    ]);
    setActivity((prev) =>
      [
        {
          id: `activity-${id}`,
          agent: agentName,
          tone: approved ? ("green" as const) : ("amber" as const),
          timeAgo: "just now",
          description: feedLine,
        },
        ...prev,
      ].slice(0, FEED_LIMIT),
    );
  }

  function toggleRule(id: string) {
    setRules((prev) =>
      prev.map((rule) =>
        rule.id === id ? { ...rule, value: rule.value === "Auto" ? "Ask first" : "Auto" } : rule,
      ),
    );
  }

  const store: EventStore = {
    approvals,
    decisions,
    activity,
    autoApproveLimit,
    rules,
    approve: (id) => decide(id, true),
    decline: (id) => decide(id, false),
    setAutoApproveLimit,
    toggleRule,
  };

  // createElement instead of JSX keeps this hooks file a plain .ts module.
  return createElement(EventContext.Provider, { value: store }, children);
}

export function useEvent(): EventStore {
  const store = useContext(EventContext);
  if (!store) throw new Error("useEvent must be used inside <EventProvider>.");
  return store;
}
