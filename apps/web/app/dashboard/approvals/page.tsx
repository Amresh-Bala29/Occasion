import { ApprovalsPanel } from "@/components/ApprovalsPanel";
import { Topbar } from "@/components/Topbar";
import { getDashboardData } from "@/lib/api";

export default async function ApprovalsPage() {
  const data = await getDashboardData();

  return (
    <>
      <Topbar section="Approvals" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <ApprovalsPanel />
    </>
  );
}
