"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { editSuggestedEvent, listCalendarEvents, listSuggestedEvents, reviewSuggestedEvent } from "@/features/calendar/api";
import type { CalendarEventAPI, SuggestedEventAPI, SuggestionEdits } from "@/features/calendar/api";

// Mailboxes are scanned in the background, so new suggestions are fetched every minute while the
// dashboard is visible, and as soon as the caregiver comes back to it.
const REFRESH_MS = 60_000;

export type EventKind = "Appointment" | "Visit" | "Deadline";

export type CalEvent = {
  id?: string;
  day: number;
  /** ISO YYYY-MM-DD when known; absent when a suggestion carries no date yet. */
  date?: string;
  title: string;
  time?: string;
  kind: EventKind;
  suggested?: boolean;
  description?: string;
};

export type Cell = { day: number; inMonth: boolean };

function toCalEvent(e: CalendarEventAPI | SuggestedEventAPI, suggested: boolean): CalEvent {
  return {
    id: e.id, day: e.day, date: e.date ?? undefined, title: e.title, time: e.time,
    kind: e.kind as EventKind, suggested, description: e.description,
  };
}

function buildCells(year: number, month: number): Cell[] {
  const firstWeekday = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const prevDays = new Date(year, month, 0).getDate();
  const cells: Cell[] = [];
  for (let i = firstWeekday - 1; i >= 0; i--) cells.push({ day: prevDays - i, inMonth: false });
  for (let d = 1; d <= daysInMonth; d++) cells.push({ day: d, inMonth: true });
  let next = 1;
  while (cells.length < 42) cells.push({ day: next++, inMonth: false });
  return cells;
}

/** Committed calendar events, pending email suggestions, and the month being viewed. */
export function useCalendar(notify: (message: string) => void) {
  const now = new Date();
  const [viewYear, setViewYear] = useState(now.getFullYear());
  const [viewMonth, setViewMonth] = useState(now.getMonth()); // 0-indexed
  const [suggestions, setSuggestions] = useState<SuggestedEventAPI[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<CalEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  // Suggestions that appeared since the previous load (none on the first), to animate in.
  const [arrived, setArrived] = useState<ReadonlySet<string>>(new Set());
  const known = useRef<ReadonlySet<string> | null>(null);

  // Suggestions and committed events load together so the grid and the review panel stay
  // consistent, and a failure surfaces a retry rather than a silently empty calendar. State is
  // only touched after the awaited calls resolve, so this is safe to call from an effect.
  const load = useCallback(async () => {
    try {
      const [sug, cal] = await Promise.all([listSuggestedEvents(), listCalendarEvents()]);
      const previous = known.current;
      known.current = new Set(sug.map((s) => s.id));
      setArrived(previous ? new Set(sug.filter((s) => !previous.has(s.id)).map((s) => s.id)) : new Set());
      setSuggestions(sug);
      setCalendarEvents(cal.map((e) => toCalEvent(e, false)));
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // load() only sets state after its request resolves, so this cannot cascade renders.
    void load();
    const refresh = () => { if (document.visibilityState === "visible") void load(); };
    const timer = setInterval(refresh, REFRESH_MS);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [load]);

  const retry = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    await load();
  }, [load]);

  // Only suggestions awaiting a decision are reviewed; accepted ones become calendar events.
  const pending = suggestions.filter((s) => s.status === "pending");
  // Pending suggestions that carry a date are previewed on the grid, styled as tentative.
  const events = [...calendarEvents, ...pending.filter((s) => s.date).map((s) => toCalEvent(s, true))];

  /** Whether the decision was saved; the panel brings the suggestion back when it wasn't. */
  const review = async (s: SuggestedEventAPI, decision: "accepted" | "dismissed"): Promise<boolean> => {
    if (decision === "accepted" && !s.date) {
      notify("Add a date before accepting — this suggestion needs review.");
      return false;
    }
    try {
      await reviewSuggestedEvent(s.id, decision);
      notify(decision === "accepted" ? "Added to your calendar" : "Suggestion dismissed");
      await load();
      return true;
    } catch {
      notify(decision === "accepted" ? "Couldn't accept — try again." : "Couldn't dismiss — try again.");
      return false;
    }
  };

  const edit = async (s: SuggestedEventAPI, edits: SuggestionEdits): Promise<boolean> => {
    try {
      await editSuggestedEvent(s.id, edits);
      notify("Suggestion updated");
      await load();
      return true;
    } catch {
      notify("Couldn't save your changes — try again.");
      return false;
    }
  };

  const cells = useMemo(() => buildCells(viewYear, viewMonth), [viewYear, viewMonth]);
  const goToMonth = (delta: number) => {
    const d = new Date(viewYear, viewMonth + delta, 1);
    setViewYear(d.getFullYear());
    setViewMonth(d.getMonth());
  };
  const goToday = () => {
    const t = new Date();
    setViewYear(t.getFullYear());
    setViewMonth(t.getMonth());
  };

  return { viewYear, viewMonth, cells, events, pending, arrived, loading, failed, retry, review, edit, goToMonth, goToday };
}
