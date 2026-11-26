"use client";

import { Globe } from "lucide-react";

import { US_TIMEZONES, timezoneLabel } from "@/features/calendar/timezone";

/** The calendar's time zone, in its top bar. Emails that give a time without a zone use it. */
export function TimezoneSetting({ timezone, onChange }: {
  timezone: string | null;
  onChange: (zone: string) => void;
}) {
  const options = timezone && !US_TIMEZONES.some((z) => z.zone === timezone)
    ? [...US_TIMEZONES, { zone: timezone, label: timezoneLabel(timezone) }] : US_TIMEZONES;
  return (
    <div className="relative">
      <Globe className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
      <select
        aria-label="Calendar time zone"
        title="Emails that give a time without a time zone use this one"
        className="h-7 rounded-md border border-input bg-card pr-2 pl-7 text-[0.8rem] text-foreground shadow-xs focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
        value={timezone ?? ""}
        onChange={(e) => onChange(e.target.value)}
      >
        {!timezone && <option value="" disabled>Time zone</option>}
        {options.map((z) => (
          <option key={z.zone} value={z.zone}>
            {z.label} time
          </option>
        ))}
      </select>
    </div>
  );
}
