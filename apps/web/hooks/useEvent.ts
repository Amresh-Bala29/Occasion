"use client";

// Client-side store for the event state that spans panels: pending approvals,
// decision history, the live activity feed, and spending rules. Deciding an
// approval here updates the sidebar badge, overview KPIs, activity rail, and
// approvals page together. Initial data is fetched on the server and passed in
// by the dashboard layout; mutations update optimistically, then persist.
import { useRouter } from "next/navigation";
import { createContext, createElement, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { getActivity, resolveApproval, saveAutoApproveLimit, toggleSpendingRule } from "@/lib/api";
import type { ActivityItem, ApprovalItem, DecisionRecord, SpendingRule } from "@/types";

interface EventStore {
  eventId: string;
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

/** Store data fetched on the server and handed to the provider by the layout. */
export interface EventInitialData {
  eventId: string;
  approvals: ApprovalItem[];
  decisions: DecisionRecord[];
  activity: ActivityItem[];
  autoApproveLimit: string;
  rules: SpendingRule[];
}

const EventContext = createContext<EventStore | null>(null);

const FEED_LIMIT = 8;
const ACTIVITY_POLL_MS = 12_000;

function feedSignature(items: ActivityItem[]): string {
  return items
    .slice(0, FEED_LIMIT)
    .map((item) => item.id)
    .join("|");
}

export function EventProvider({ children, initial }: { children: ReactNode; initial: EventInitialData }) {
  const eventId = initial.eventId;
  const router = useRouter();
  const [approvals, setApprovals] = useState(initial.approvals);
  const [decisions, setDecisions] = useState(initial.decisions);
  const [activity, setActivity] = useState(initial.activity);
  const [autoApproveLimit, setLimit] = useState(initial.autoApproveLimit);
  const [rules, setRules] = useState(initial.rules);
  // Ids only — timeAgo strings shift every poll and would refresh forever.
  const lastFeedIds = useRef(feedSignature(initial.activity));
  const inFlight = useRef(false);

  // The real feed: background runs and approval decisions write activity rows,
  // and the rail polls them. A failed poll keeps the last good list. New rows are
  // also the one signal that agent output landed server-side, so a feed change
  // refreshes every server component (overview, vendors, plan, budget, deadlines)
  // while this store's client state stays put.
  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      if (inFlight.current) return; // a slow response must not stack overlapping polls
      inFlight.current = true;
      getActivity(eventId)
        .then((items) => {
          if (cancelled) return;
          setActivity(items.slice(0, FEED_LIMIT));
          const signature = feedSignature(items);
          if (signature !== lastFeedIds.current) {
            lastFeedIds.current = signature;
            router.refresh();
          }
        })
        .catch(() => {})
        .finally(() => {
          inFlight.current = false;
        });
    };
    const timer = setInterval(poll, ACTIVITY_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [eventId, router]);

  function decide(id: string, approved: boolean) {
    const item = approvals.find((approval) => approval.id === id);
    if (!item) return;
    const agentName = item.agent.replace(/ agent$/i, "");
    const feedLine = approved
      ? `You approved ${item.title} — ${item.amount}. The ${agentName} agent is proceeding now.`
      : `You declined ${item.title}. The ${agentName} agent will source an alternative.`;

    // Optimistic: reflect the decision across every panel immediately, then persist.
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

    // Money-sensitive: roll the optimistic update back if the write doesn't land.
    void resolveApproval(id, approved).catch(() => {
      setApprovals((prev) => (prev.some((approval) => approval.id === id) ? prev : [item, ...prev]));
      setDecisions((prev) => prev.filter((decision) => decision.id !== `decision-${id}`));
      setActivity((prev) => prev.filter((entry) => entry.id !== `activity-${id}`));
    });
  }

  function toggleRule(id: string) {
    setRules((prev) =>
      prev.map((rule) =>
        rule.id === id ? { ...rule, value: rule.value === "Auto" ? "Ask first" : "Auto" } : rule,
      ),
    );
    void toggleSpendingRule(eventId, id).catch(() => {});
  }

  function setAutoApproveLimit(limit: string) {
    setLimit(limit);
    void saveAutoApproveLimit(eventId, limit).catch(() => {});
  }

  const store: EventStore = {
    eventId,
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
