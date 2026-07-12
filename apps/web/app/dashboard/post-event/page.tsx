import { PostEventPanel } from "@/components/PostEventPanel";
import { Topbar } from "@/components/Topbar";
import { getDashboardData, getPostEventTasks } from "@/lib/api";

export default async function PostEventPage() {
  const [data, tasks] = await Promise.all([getDashboardData(), getPostEventTasks()]);

  return (
    <>
      <Topbar section="Post-event" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <PostEventPanel event={data.event} tasks={tasks} />
    </>
  );
}
