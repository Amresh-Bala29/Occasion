import { TaskBoard } from "@/components/TaskBoard";
import { Topbar } from "@/components/Topbar";
import { getDashboardData } from "@/lib/api";

export default function PlanPage() {
  const data = getDashboardData();

  return (
    <>
      <Topbar section="Plan" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <TaskBoard eventId={data.event.id} />
    </>
  );
}
