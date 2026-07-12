import { cookies } from "next/headers";

import { Topbar } from "@/components/Topbar";
import { VendorsPanel } from "@/components/VendorCard";
import { DEFAULT_EVENT_ID, EVENT_COOKIE, getDashboardData, getVendors } from "@/lib/api";

export default async function VendorsPage() {
  const eventId = (await cookies()).get(EVENT_COOKIE)?.value ?? DEFAULT_EVENT_ID;
  const [data, vendors] = await Promise.all([getDashboardData(eventId), getVendors(eventId)]);

  return (
    <>
      <Topbar section="Vendors" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      <VendorsPanel initialVendors={vendors} />
    </>
  );
}
