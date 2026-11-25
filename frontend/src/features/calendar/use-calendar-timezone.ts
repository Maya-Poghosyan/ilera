"use client";

import { useEffect, useState } from "react";

import { getCalendarTimezone, setCalendarTimezone, type CalendarTimezone } from "@/features/calendar/api";

/** The calendar's time zone and a way to change it. */
export function useCalendarTimezone(caseId: string | null | undefined, notify: (message: string) => void) {
  const [current, setCurrent] = useState<CalendarTimezone & { caseId: string } | null>(null);

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    getCalendarTimezone(caseId)
      .then((tz) => { if (!cancelled) setCurrent({ ...tz, caseId }); })
      .catch(() => { /* the picker stays empty; events show as written */ });
    return () => { cancelled = true; };
  }, [caseId]);

  const value = current?.caseId === caseId ? current : null;

  async function change(zone: string) {
    if (!caseId) return;
    try {
      setCurrent({ ...(await setCalendarTimezone(caseId, zone)), caseId });
      notify("Time zone saved. Emails without a time zone use it from now on.");
    } catch {
      notify("Couldn't save the time zone — try again.");
    }
  }

  return { timezone: value?.timezone ?? null, source: value?.source ?? null, change };
}
