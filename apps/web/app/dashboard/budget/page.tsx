import { BudgetTracker } from "@/components/BudgetTracker";
import { Topbar } from "@/components/Topbar";
import { getDashboardData } from "@/lib/api";

export default async function BudgetPage() {
  const data = await getDashboardData();

  return (
    <>
      <Topbar section="Budget" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <BudgetTracker />
    </>
  );
}
