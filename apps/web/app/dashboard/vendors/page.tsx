import { Topbar } from "@/components/Topbar";
import { VendorsPanel } from "@/components/VendorCard";
import { getDashboardData, getVendors } from "@/lib/api";

export default async function VendorsPage() {
  const [data, vendors] = await Promise.all([getDashboardData(), getVendors()]);

  return (
    <>
      <Topbar section="Vendors" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <VendorsPanel initialVendors={vendors} />
    </>
  );
}
