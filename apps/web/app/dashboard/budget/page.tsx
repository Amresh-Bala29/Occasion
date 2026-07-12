import { cookies } from "next/headers";

import { BudgetTracker } from "@/components/BudgetTracker";
import { Topbar } from "@/components/Topbar";
import { DEFAULT_EVENT_ID, EVENT_COOKIE, getDashboardData } from "@/lib/api";

export default async function BudgetPage() {
  const eventId = (await cookies()).get(EVENT_COOKIE)?.value ?? DEFAULT_EVENT_ID;
  const data = await getDashboardData(eventId);

  return (
    <>
      <Topbar section="Budget" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <BudgetTracker eventId={eventId} />
    </>
  );
}
