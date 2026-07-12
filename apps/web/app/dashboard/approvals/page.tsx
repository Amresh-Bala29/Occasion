import { cookies } from "next/headers";

import { ApprovalsPanel } from "@/components/ApprovalsPanel";
import { Topbar } from "@/components/Topbar";
import { DEFAULT_EVENT_ID, EVENT_COOKIE, getDashboardData } from "@/lib/api";

export default async function ApprovalsPage() {
  const eventId = (await cookies()).get(EVENT_COOKIE)?.value ?? DEFAULT_EVENT_ID;
  const data = await getDashboardData(eventId);

  return (
    <>
      <Topbar section="Settings" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <ApprovalsPanel event={data.event} />
    </>
  );
}
