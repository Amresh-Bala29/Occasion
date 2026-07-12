import { EventDashboard } from "@/components/EventDashboard";
import { getDashboardData, getKeyDeadlines, getVendors } from "@/lib/api";

export default async function DashboardPage() {
  const [data, vendors, deadlines] = await Promise.all([
    getDashboardData(),
    getVendors(),
    getKeyDeadlines(),
  ]);

  return <EventDashboard data={data} vendors={vendors} deadlines={deadlines} />;
}
