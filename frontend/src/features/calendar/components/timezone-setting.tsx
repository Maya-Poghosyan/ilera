"use client";

import { Globe } from "lucide-react";

import { US_TIMEZONES, timezoneLabel } from "@/features/calendar/timezone";

/** The calendar's time zone, next to its title. Emails that give a time without a zone use it. */
export function TimezoneSetting({ timezone, source, onChange }: {
  timezone: string | null;
  source: "setting" | "intake" | null;
  onChange: (zone: string) => void;
}) {
  const options = timezone && !US_TIMEZONES.some((z) => z.zone === timezone)
    ? [...US_TIMEZONES, { zone: timezone, label: timezoneLabel(timezone) }] : US_TIMEZONES;
  return (
    <label className="flex items-center gap-2 text-sm text-muted-foreground">
      <Globe className="size-4" aria-hidden="true" />
      <span className="sr-only">Calendar time zone</span>
      <select
        aria-label="Calendar time zone"
        className="rounded-md border border-input bg-card px-2 py-1 text-sm text-foreground"
        value={timezone ?? ""}
        onChange={(e) => onChange(e.target.value)}
      >
        {!timezone && <option value="" disabled>Choose time zone</option>}
        {options.map((z) => <option key={z.zone} value={z.zone}>{z.label} time</option>)}
      </select>
      {source === "intake" && <span className="text-xs">from your intake</span>}
    </label>
  );
}
