import { cookies } from "next/headers";

import { PostEventPanel } from "@/components/PostEventPanel";
import { Topbar } from "@/components/Topbar";
import { DEFAULT_EVENT_ID, EVENT_COOKIE, getDashboardData, getPostEventTasks } from "@/lib/api";

export default async function PostEventPage() {
  const eventId = (await cookies()).get(EVENT_COOKIE)?.value ?? DEFAULT_EVENT_ID;
  const [data, tasks] = await Promise.all([getDashboardData(eventId), getPostEventTasks(eventId)]);

  return (
    <>
      <Topbar section="Post-event" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <PostEventPanel event={data.event} tasks={tasks} />
    </>
  );
}
