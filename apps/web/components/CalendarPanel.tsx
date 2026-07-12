"use client";

import { useState } from "react";
import type { CalendarEventItem, CalendarEventKind, DeadlineItem } from "@/types";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const KIND_CLASSES: Record<CalendarEventKind, string> = {
  warn: "bg-warn-soft text-warn-deep",
  info: "bg-brand-soft text-brand-deep",
  accent: "bg-brand text-white",
  muted: "bg-[#eef0f4] text-ink-soft",
};

/** One month-grid cell: null day means a leading/trailing blank. */
interface DayCell {
  day: number | null;
  events: CalendarEventItem[];
}

/** Parse "2026-08-06" into local-date parts; new Date(iso) would shift across timezones. */
function parseIsoDay(iso: string): { year: number; month: number; day: number } {
  const [year, month, day] = iso.split("-").map(Number);
  return { year, month: month - 1, day };
}

function buildMonthCells(monthStart: Date, events: CalendarEventItem[]): DayCell[] {
  const year = monthStart.getFullYear();
  const month = monthStart.getMonth();

  const eventsByDay = new Map<number, CalendarEventItem[]>();
  for (const event of events) {
    const date = parseIsoDay(event.date);
    if (date.year !== year || date.month !== month) continue;
    const bucket = eventsByDay.get(date.day) ?? [];
    bucket.push(event);
    eventsByDay.set(date.day, bucket);
  }

  const cells: DayCell[] = [];
  for (let i = 0; i < monthStart.getDay(); i++) cells.push({ day: null, events: [] });
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  for (let day = 1; day <= daysInMonth; day++) {
    cells.push({ day, events: eventsByDay.get(day) ?? [] });
  }
  while (cells.length % 7 !== 0) cells.push({ day: null, events: [] });
  return cells;
}

/** Open on the event day's month (the accent marker) so the grid lands on the action;
 *  fall back to the earliest event, then the current month. */
function initialMonth(events: CalendarEventItem[]): Date {
  const anchor = events.find((event) => event.kind === "accent") ?? events[0];
  if (!anchor) return new Date();
  const { year, month } = parseIsoDay(anchor.date);
  return new Date(year, month, 1);
}

/** Calendar tab: navigable month grid of event deadlines plus the "Upcoming" rail. */
export function CalendarPanel({ events, agenda }: { events: CalendarEventItem[]; agenda: DeadlineItem[] }) {
  const [monthStart, setMonthStart] = useState(() => initialMonth(events));

  const shiftMonth = (delta: number) =>
    setMonthStart((current) => new Date(current.getFullYear(), current.getMonth() + delta, 1));

  return (
    <div className="flex flex-col gap-6 lg:flex-row">
      <section className="min-w-0 flex-1" aria-label="Month calendar">
        <div className="mb-[18px] flex items-center justify-between">
          <h1 className="font-serif text-[28px] font-medium tracking-[-0.01em]">
            {monthStart.toLocaleString("en-US", { month: "long" })} {monthStart.getFullYear()}
          </h1>
          <div className="flex gap-2">
            <MonthNavButton label="Previous month" glyph="‹" onClick={() => shiftMonth(-1)} />
            <MonthNavButton label="Next month" glyph="›" onClick={() => shiftMonth(1)} />
          </div>
        </div>
        <MonthGrid monthStart={monthStart} events={events} />
      </section>

      <section className="w-full flex-none lg:w-[300px]" aria-label="Upcoming deadlines">
        <h2 className="mb-[13px] text-[16px] font-semibold">Upcoming</h2>
        <div className="flex flex-col gap-2.5">
          {agenda.map((item) => (
            <AgendaCard key={item.id} item={item} />
          ))}
        </div>
      </section>
    </div>
  );
}

function MonthNavButton({
  label,
  glyph,
  onClick,
}: {
  label: string;
  glyph: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="size-[34px] cursor-pointer rounded-[9px] border border-line-strong bg-surface text-[15px] text-ink-soft hover:bg-[#f6f8fc]"
    >
      {glyph}
    </button>
  );
}

function MonthGrid({ monthStart, events }: { monthStart: Date; events: CalendarEventItem[] }) {
  const cells = buildMonthCells(monthStart, events);
  return (
    <div className="card overflow-hidden rounded-[16px]">
      <div className="grid grid-cols-7 border-b border-[#eef0f4]">
        {WEEKDAYS.map((weekday) => (
          <div
            key={weekday}
            className="py-2.5 text-center font-mono text-[10px] tracking-[0.06em] text-ink-faint uppercase"
          >
            {weekday}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {cells.map((cell, index) => (
          <DayCellView key={index} cell={cell} monthStart={monthStart} />
        ))}
      </div>
    </div>
  );
}

function DayCellView({ cell, monthStart }: { cell: DayCell; monthStart: Date }) {
  if (cell.day === null) {
    return <div className="min-h-[92px] border-r border-b border-[#f2f4f7] bg-[#fbfcfd] p-[7px_8px]" />;
  }

  // The event day (an "accent" item) gets a filled circle and a tinted cell.
  const isEventDay = cell.events.some((event) => event.kind === "accent");
  const today = new Date();
  const isToday =
    today.getFullYear() === monthStart.getFullYear() &&
    today.getMonth() === monthStart.getMonth() &&
    today.getDate() === cell.day;

  const circleClasses = [
    "flex size-[22px] items-center justify-center rounded-full text-[12.5px]",
    cell.events.length > 0 ? "font-bold" : "font-medium",
    isEventDay ? "bg-brand text-white" : "text-ink",
    isToday ? "ring-2 ring-brand-mist" : "",
  ].join(" ");

  return (
    <div
      className={`min-h-[92px] border-r border-b border-[#f2f4f7] p-[7px_8px] ${
        isEventDay ? "bg-brand-soft" : "bg-surface"
      }`}
    >
      <div className={circleClasses}>{cell.day}</div>
      <div className="mt-1 flex flex-col gap-[3px]">
        {cell.events.map((event) => (
          <div
            key={event.title}
            className={`rounded-[5px] px-1.5 py-[3px] text-[10.5px] leading-[1.25] font-semibold ${KIND_CLASSES[event.kind]}`}
          >
            {event.title}
          </div>
        ))}
      </div>
    </div>
  );
}

function AgendaCard({ item }: { item: DeadlineItem }) {
  const metaColor = item.emphasis === "urgent" ? "text-warn-strong" : "text-ink-faint";
  const dayColor = item.emphasis === "event" ? "text-brand" : "text-ink";

  return (
    <div className="card flex items-start gap-[13px] rounded-[12px] px-[15px] py-[13px]">
      <div className="w-[42px] flex-none text-center">
        <div className={`font-mono text-[9.5px] tracking-[0.05em] uppercase ${metaColor}`}>{item.month}</div>
        <div className={`text-[19px] leading-none font-bold ${dayColor}`}>{item.day}</div>
      </div>
      <div className="w-px self-stretch bg-[#eceff4]" aria-hidden="true" />
      <div className="min-w-0">
        <div className="text-[13px] font-semibold">{item.title}</div>
        <div className={`mt-0.5 text-[11.5px] ${metaColor}`}>{item.meta}</div>
      </div>
    </div>
  );
}
