import { cookies } from "next/headers";

import { MessagesInbox } from "@/components/MessagesInbox";
import { Topbar } from "@/components/Topbar";
import { DEFAULT_EVENT_ID, EVENT_COOKIE, getDashboardData, getInboxConversations } from "@/lib/api";

export default async function MessagesPage({
  searchParams,
}: {
  searchParams: Promise<{ thread?: string }>;
}) {
  // Approval cards deep-link here as /dashboard/messages?thread=<id>.
  const { thread } = await searchParams;
  const eventId = (await cookies()).get(EVENT_COOKIE)?.value ?? DEFAULT_EVENT_ID;
  const [data, conversations] = await Promise.all([
    getDashboardData(eventId),
    getInboxConversations(eventId),
  ]);

  return (
    <>
      <Topbar section="Messages" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <MessagesInbox initialConversations={conversations} initialThreadId={thread} />
    </>
  );
}
