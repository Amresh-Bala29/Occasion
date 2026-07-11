import { Topbar } from "@/components/Topbar";
import { VendorsPanel } from "@/components/VendorCard";
import { getDashboardData } from "@/lib/api";

export default function VendorsPage() {
  const data = getDashboardData();

  return (
    <>
      <Topbar section="Vendors" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <VendorsPanel />
    </>
  );
}
