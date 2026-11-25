import { ChevronLeft, ChevronRight, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { zoneSuffix } from "@/features/calendar/timezone";
import type { CalEvent, Cell } from "@/features/calendar/use-calendar";
import { cn } from "@/lib/utils";

const WEEKDAY_HEADERS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// Events carrying a date only belong on the grid when it falls in the shown month.
function inMonth(e: CalEvent, year: number, month: number): boolean {
  if (!e.date) return false;
  const [y, m] = e.date.split("-").map(Number);
  return y === year && m === month + 1;
}

export function MonthGrid({ year, month, cells, events, timezone, actions, onMonth, onToday }: {
  year: number;
  month: number; // 0-indexed
  cells: Cell[];
  events: CalEvent[];
  /** The calendar's zone; an event in another zone shows its zone's name. */
  timezone: string | null;
  /** Controls shown in the top bar, before the month navigation. */
  actions?: ReactNode;
  onMonth: (delta: number) => void;
  onToday: () => void;
}) {
  const now = new Date();
  // Highlight today's cell only when the calendar is showing the current month.
  const todayDay = now.getFullYear() === year && now.getMonth() === month ? now.getDate() : -1;
  const monthName = new Date(year, month, 1).toLocaleString("en-US", { month: "long" });
  return (
    <div className="overflow-hidden rounded-xl border border-brand-subtle bg-card shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-brand-subtle bg-brand-subtle/40 px-4 py-3">
        <h2 className="text-lg">{monthName} {year}</h2>
        <div className="flex items-center gap-3">
          {actions}
          <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon-sm" aria-label="Previous month" onClick={() => onMonth(-1)}>
            <ChevronLeft />
          </Button>
          <Button variant="outline" size="sm" onClick={onToday}>Today</Button>
          <Button variant="ghost" size="icon-sm" aria-label="Next month" onClick={() => onMonth(1)}>
            <ChevronRight />
          </Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-7 border-b border-brand-subtle bg-brand-subtle/50">
        {WEEKDAY_HEADERS.map((w) => (
          <div key={w} className="px-2 py-2 text-center text-xs font-medium text-primary">{w}</div>
        ))}
      </div>

      <div className="grid grid-cols-7">
        {cells.map((cell, i) => {
          const isToday = cell.inMonth && cell.day === todayDay;
          const dayEvents = cell.inMonth ? events.filter((e) => e.day === cell.day && inMonth(e, year, month)) : [];
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
                      : cell.inMonth ? "text-foreground" : "text-muted-foreground/50",
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
                    title={e.time ? `${e.title} · ${e.time}${zoneSuffix(e.timezone, e.date, timezone)}` : e.title}
                  >
                    {e.suggested && <Sparkles className="mb-0.5 inline size-2.5" />}{" "}
                    {e.time && <span className="tabular-nums">{e.time}{zoneSuffix(e.timezone, e.date, timezone)} </span>}
                    {e.title}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
