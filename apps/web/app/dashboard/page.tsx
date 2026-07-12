import { cookies } from "next/headers";

import { EventDashboard } from "@/components/EventDashboard";
import { DEFAULT_EVENT_ID, EVENT_COOKIE, getDashboardData, getKeyDeadlines, getVendors } from "@/lib/api";

export default async function DashboardPage() {
  const eventId = (await cookies()).get(EVENT_COOKIE)?.value ?? DEFAULT_EVENT_ID;
  const [data, vendors, deadlines] = await Promise.all([
    getDashboardData(eventId),
    getVendors(eventId),
    getKeyDeadlines(eventId),
  ]);

  return <EventDashboard data={data} vendors={vendors} deadlines={deadlines} />;
}
