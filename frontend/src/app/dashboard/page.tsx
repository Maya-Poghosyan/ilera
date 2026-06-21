import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type EventKind = "Appointment" | "Visit" | "Deadline";

type CalEvent = {
  day: number;
  title: string;
  time?: string;
  kind: EventKind;
};

const YEAR = 2026;
const MONTH = 5; // June (0-indexed)
const TODAY = 21;

const events: CalEvent[] = [
  { day: 23, title: "Dr. Patel — cardiology follow-up", time: "10:00 AM", kind: "Appointment" },
  { day: 25, title: "County social worker visit", time: "2:00 PM", kind: "Visit" },
  { day: 27, title: "IHSS timesheet due", kind: "Deadline" },
];

const kindStyle: Record<EventKind, string> = {
  Appointment: "bg-brand-subtle text-primary",
  Visit: "bg-amber-100 text-amber-800",
  Deadline: "bg-rose-100 text-rose-700",
};

const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const monthName = new Date(YEAR, MONTH, 1).toLocaleString("en-US", { month: "long" });

type Cell = { day: number; inMonth: boolean };

function buildCells(): Cell[] {
  const firstWeekday = new Date(YEAR, MONTH, 1).getDay();
  const daysInMonth = new Date(YEAR, MONTH + 1, 0).getDate();
  const prevDays = new Date(YEAR, MONTH, 0).getDate();

  const cells: Cell[] = [];
  for (let i = firstWeekday - 1; i >= 0; i--) {
    cells.push({ day: prevDays - i, inMonth: false });
  }
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ day: d, inMonth: true });
  }
  let next = 1;
  while (cells.length < 42) {
    cells.push({ day: next++, inMonth: false });
  }
  return cells;
}

export default function CalendarPage() {
  const cells = buildCells();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Care Calendar</h1>
          <p className="text-sm text-muted-foreground">
            Agents can scan email (via Poke) to auto-create events and text reminders.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">+ Appointment</Button>
          <Button variant="outline" size="sm">+ Visit</Button>
          <Button variant="outline" size="sm">+ Deadline</Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-xs">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-lg font-semibold">
            {monthName} {YEAR}
          </h2>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon-sm" aria-label="Previous month">
              <ChevronLeft />
            </Button>
            <Button variant="outline" size="sm">Today</Button>
            <Button variant="ghost" size="icon-sm" aria-label="Next month">
              <ChevronRight />
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-7 border-b border-border bg-muted/40">
          {weekdays.map((w) => (
            <div
              key={w}
              className="px-2 py-2 text-center text-xs font-medium text-muted-foreground"
            >
              {w}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7">
          {cells.map((cell, i) => {
            const isToday = cell.inMonth && cell.day === TODAY;
            const dayEvents = cell.inMonth
              ? events.filter((e) => e.day === cell.day)
              : [];
            return (
              <div
                key={i}
                className={cn(
                  "min-h-28 border-b border-r border-border p-1.5 last:border-r-0",
                  (i + 1) % 7 === 0 && "border-r-0",
                  i >= 35 && "border-b-0",
                  !cell.inMonth && "bg-muted/30",
                )}
              >
                <div className="mb-1 flex justify-end">
                  <span
                    className={cn(
                      "flex size-6 items-center justify-center rounded-full text-xs",
                      isToday
                        ? "bg-primary font-semibold text-primary-foreground"
                        : cell.inMonth
                          ? "text-foreground"
                          : "text-muted-foreground/50",
                    )}
                  >
                    {cell.day}
                  </span>
                </div>
                <div className="space-y-1">
                  {dayEvents.map((e) => (
                    <div
                      key={e.title}
                      className={cn(
                        "truncate rounded-md px-1.5 py-1 text-[11px] font-medium leading-tight",
                        kindStyle[e.kind],
                      )}
                      title={e.time ? `${e.title} · ${e.time}` : e.title}
                    >
                      {e.time && <span className="tabular-nums">{e.time} </span>}
                      {e.title}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
