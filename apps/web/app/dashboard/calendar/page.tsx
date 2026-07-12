import { CalendarPanel } from "@/components/CalendarPanel";
import { Topbar } from "@/components/Topbar";
import { getCalendarAgenda, getCalendarEvents, getDashboardData } from "@/lib/api";

export default async function CalendarPage() {
  const [data, events, agenda] = await Promise.all([
    getDashboardData(),
    getCalendarEvents(),
    getCalendarAgenda(),
  ]);

  return (
    <>
      <Topbar section="Calendar" eventName={data.event.name} agentsWorking={data.agentsWorking} />
      {/* Wider column than other tabs so the month grid + agenda rail fit side by side. */}
      <main className="mx-auto flex w-full max-w-[1200px] flex-col px-6 pt-[22px] pb-10">
        <CalendarPanel events={events} agenda={agenda} />
      </main>
    </>
  );
}
