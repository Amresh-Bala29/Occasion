import { PostEventPanel } from "@/components/PostEventPanel";
import { Topbar } from "@/components/Topbar";
import { getDashboardData } from "@/lib/api";

export default function PostEventPage() {
  const data = getDashboardData();

  return (
    <>
      <Topbar section="Post-event" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <PostEventPanel />
    </>
  );
}
