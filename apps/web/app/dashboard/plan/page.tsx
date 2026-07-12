import { cookies } from "next/headers";

import { TaskBoard } from "@/components/TaskBoard";
import { Topbar } from "@/components/Topbar";
import { DEFAULT_EVENT_ID, EVENT_COOKIE, getDashboardData, getEventPlan } from "@/lib/api";

export default async function PlanPage() {
  const eventId = (await cookies()).get(EVENT_COOKIE)?.value ?? DEFAULT_EVENT_ID;
  const [data, plan] = await Promise.all([getDashboardData(eventId), getEventPlan(eventId)]);

  return (
    <>
      <Topbar section="Plan" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <TaskBoard eventId={data.event.id} plan={plan} />
    </>
  );
}
