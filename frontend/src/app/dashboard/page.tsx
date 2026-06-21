import { Check, ChevronLeft, ChevronRight, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type EventKind = "Appointment" | "Visit" | "Deadline";

type CalEvent = {
  day: number;
  title: string;
  time?: string;
  kind: EventKind;
  suggested?: boolean;
  description?: string;
};

const YEAR = 2026;
const MONTH = 5; // June (0-indexed)
const TODAY = 21;

const events: CalEvent[] = [
  { day: 23, title: "Dr. Patel — cardiology follow-up", time: "10:00 AM", kind: "Appointment" },
  { day: 25, title: "County social worker visit", time: "2:00 PM", kind: "Visit" },
  { day: 27, title: "IHSS timesheet due", kind: "Deadline" },
];

const suggestedEvents: CalEvent[] = [
  { day: 24, title: "Pharmacy refill pickup", time: "9:00 AM", kind: "Appointment", suggested: true, description: "Found in email from CVS — prescription #4021 ready for pickup at Main St location." },
  { day: 28, title: "IHSS pay stub review", kind: "Deadline", suggested: true, description: "IHSS direct deposit scheduled for Jun 28. Review hours logged against pay stub." },
];

const allEvents = [...events, ...suggestedEvents];

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

function SuggestedEventsPanel() {
  return (
    <div className="rounded-xl border border-brand-subtle bg-brand-subtle/30 p-4 space-y-3">
      <div className="flex items-center gap-2 text-primary">
        <Sparkles className="size-4" />
        <h3 className="text-sm font-semibold">Suggested Events</h3>
      </div>
      <p className="text-xs text-muted-foreground">
        Detected from recent emails and documents. Accept to add to your calendar.
      </p>
      <div className="space-y-2">
        {suggestedEvents.map((e) => (
          <div
            key={e.title}
            className="flex items-start justify-between rounded-lg border border-dashed border-primary/30 bg-white px-3 py-2.5"
          >
            <div className="min-w-0 flex-1 space-y-1">
              <p className="text-sm font-medium text-foreground">{e.title}</p>
              <p className="text-xs text-muted-foreground">
                {monthName} {e.day}{e.time ? ` · ${e.time}` : ""} · {e.kind}
              </p>
              {e.description && (
                <p className="text-xs leading-relaxed text-muted-foreground/80">
                  {e.description}
                </p>
              )}
            </div>
            <div className="ml-3 flex shrink-0 items-center gap-1 pt-0.5">
              <button
                className="flex size-7 items-center justify-center rounded-full bg-brand-subtle text-primary hover:bg-primary hover:text-white transition-colors"
                aria-label="Accept"
              >
                <Check className="size-3.5" />
              </button>
              <button
                className="flex size-7 items-center justify-center rounded-full bg-brand-subtle text-muted-foreground hover:bg-red-100 hover:text-red-600 transition-colors"
                aria-label="Dismiss"
              >
                <X className="size-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CalendarPage() {
  const cells = buildCells();

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div>
          <h1 className="text-4xl font-bold">Care Calendar</h1>
          <p className="text-sm text-muted-foreground">
            Agents can scan email to auto-create events and text reminders.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button className="px-10 hover:font-bold">+ Appointment</Button>
          <Button className="px-10 hover:font-bold">+ Visit</Button>
          <Button className="px-10 hover:font-bold">+ Deadline</Button>
        </div>
      </div>

      <SuggestedEventsPanel />

      <div className="overflow-hidden rounded-xl border border-brand-subtle bg-white shadow-xs">
        <div className="flex items-center justify-between border-b border-brand-subtle bg-brand-subtle/40 px-4 py-3">
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

        <div className="grid grid-cols-7 border-b border-brand-subtle bg-brand-subtle/50">
          {weekdays.map((w) => (
            <div
              key={w}
              className="px-2 py-2 text-center text-xs font-medium text-primary"
            >
              {w}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7">
          {cells.map((cell, i) => {
            const isToday = cell.inMonth && cell.day === TODAY;
            const dayEvents = cell.inMonth
              ? allEvents.filter((e) => e.day === cell.day)
              : [];
            return (
              <div
                key={i}
                className={cn(
                  "flex min-h-28 flex-col border-b border-r border-brand-subtle/60 p-1.5 last:border-r-0",
                  (i + 1) % 7 === 0 && "border-r-0",
                  i >= 35 && "border-b-0",
                  !cell.inMonth && "bg-brand-subtle/20",
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
                <div className="flex flex-1 flex-col gap-1">
                  {dayEvents.map((e) => (
                    <div
                      key={e.title}
                      className={cn(
                        "flex-1 rounded-md px-1.5 py-1 text-[11px] font-medium leading-tight",
                        e.suggested
                          ? "border border-dashed border-primary/40 bg-brand-subtle/50 text-primary/70"
                          : "bg-brand-subtle text-primary",
                      )}
                      title={e.time ? `${e.title} · ${e.time}` : e.title}
                    >
                      {e.suggested && <Sparkles className="mb-0.5 inline size-2.5" />}{" "}
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
