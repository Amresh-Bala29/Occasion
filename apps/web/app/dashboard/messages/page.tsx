import { MessagesInbox } from "@/components/MessagesInbox";
import { Topbar } from "@/components/Topbar";
import { getDashboardData, getInboxConversations } from "@/lib/api";

export default async function MessagesPage({
  searchParams,
}: {
  searchParams: Promise<{ thread?: string }>;
}) {
  // Approval cards deep-link here as /dashboard/messages?thread=<id>.
  const { thread } = await searchParams;
  const data = getDashboardData();

  return (
    <>
      <Topbar section="Messages" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <MessagesInbox initialConversations={getInboxConversations()} initialThreadId={thread} />
    </>
  );
}
