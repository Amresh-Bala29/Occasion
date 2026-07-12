import { TaskBoard } from "@/components/TaskBoard";
import { Topbar } from "@/components/Topbar";
import { getDashboardData, getEventPlan } from "@/lib/api";

export default async function PlanPage() {
  const [data, plan] = await Promise.all([getDashboardData(), getEventPlan()]);

  return (
    <>
      <Topbar section="Plan" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <TaskBoard eventId={data.event.id} plan={plan} />
    </>
  );
}
