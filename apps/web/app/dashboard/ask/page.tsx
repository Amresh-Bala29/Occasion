import { cookies } from "next/headers";

import { ChatPanel } from "@/components/ChatPanel";
import { Topbar } from "@/components/Topbar";
import { DEFAULT_EVENT_ID, EVENT_COOKIE, getDashboardData } from "@/lib/api";

export default async function AskOccasionPage() {
  const eventId = (await cookies()).get(EVENT_COOKIE)?.value ?? DEFAULT_EVENT_ID;
  const data = await getDashboardData(eventId);

  return (
    <>
      <Topbar section="Ask Occasion" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      {/* Chat + live browsers run on the real event (the cookie id), not data.event.id:
          a demo fixture redirects the dashboard, but the conversation and browser sessions
          live on the real event, so the workspace must key to it to stay a normal run. */}
      <ChatPanel key={eventId} eventId={eventId} mode="workspace" />
    </>
  );
}
