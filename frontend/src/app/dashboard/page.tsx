"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarDays, Check, ChevronLeft, ChevronRight, Sparkles, X } from "lucide-react";

import { MailboxConnections } from "@/components/mailbox-connections";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import {
  createReminder,
  deleteReminder,
  deleteSuggestedEvent,
  listReminders,
  listSuggestedEvents,
  updateReminder,
} from "@/lib/api";
import type { SuggestedEventAPI } from "@/lib/api";
import type {
  Reminder,
  ReminderCreate,
  ReminderKind,
  ScheduleFreq,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Calendar grid helpers
// ---------------------------------------------------------------------------

type EventKind = "Appointment" | "Visit" | "Deadline";

type CalEvent = {
  id?: string;
  day: number;
  /** ISO YYYY-MM-DD when known; absent for the hardcoded demo events. */
  date?: string;
  title: string;
  time?: string;
  kind: EventKind;
  suggested?: boolean;
  description?: string;
};

const YEAR = 2026;
const MONTH = 5; // June (0-indexed)
const TODAY = 4;

const events: CalEvent[] = [
  { day: 2, title: "Dr. Patel \u2014 cardiology follow-up", time: "10:00 AM", kind: "Appointment" },
  { day: 5, title: "County social worker visit", time: "2:00 PM", kind: "Visit" },
  { day: 9, title: "IHSS timesheet due", kind: "Deadline" },
];

// Fallback for the pre-intake demo case.
const DEFAULT_CASE_ID = "demo";

// Reminder times are wall-clock in the caregiver's own zone, not the server's.
const LOCAL_TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

function apiEventToCalEvent(e: SuggestedEventAPI): CalEvent {
  return {
    id: e.id,
    day: e.day,
    date: e.date ?? undefined,
    title: e.title,
    time: e.time,
    kind: (e.kind as EventKind) || "Appointment",
    suggested: true,
    description: e.description,
  };
}

const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const monthName = new Date(YEAR, MONTH, 1).toLocaleString("en-US", { month: "long" });

// Events carrying a date only belong on the grid when it falls in the shown month.
function isInDisplayedMonth(e: CalEvent): boolean {
  if (!e.date) return true;
  const [year, month] = e.date.split("-").map(Number);
  return year === YEAR && month === MONTH + 1;
}

function formatEventDate(e: CalEvent): string {
  if (!e.date) return e.day > 0 ? `${monthName} ${e.day}` : "";
  const [year, month, day] = e.date.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: year === YEAR ? undefined : "numeric",
  });
}

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

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------

const KIND_LABELS: Record<ReminderKind, string> = {
  daily_care_log: "Daily Care Log",
  appointment: "Appointment",
  renewal_deadline: "Renewal Deadline",
  custom: "Custom",
};

const FREQ_LABELS: Record<ScheduleFreq, string> = {
  daily: "Daily",
  weekly: "Weekly",
  once: "One-time",
};

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CalendarPage() {
  const cells = buildCells();

  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [apiSuggested, setApiSuggested] = useState<CalEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [caseId] = useState(
    () =>
      (typeof window !== "undefined" ? localStorage.getItem("ilera_case_id") : null) ??
      DEFAULT_CASE_ID
  );
  const [toast, setToast] = useState<string | null>(null);

  // Reminder form
  const [showReminderForm, setShowReminderForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formKind, setFormKind] = useState<ReminderKind>("custom");
  const [formMessage, setFormMessage] = useState("");
  const [formFreq, setFormFreq] = useState<ScheduleFreq>("daily");
  const [formTime, setFormTime] = useState("09:00");
  const [formWeekday, setFormWeekday] = useState(0);
  const [formDate, setFormDate] = useState("");

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }, []);

  const loadReminders = useCallback(async () => {
    try {
      const data = await listReminders(caseId);
      setReminders(data);
    } catch {
      // API may not be running
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  const loadSuggestedEvents = useCallback(async () => {
    try {
      const data = await listSuggestedEvents();
      setApiSuggested(data.map(apiEventToCalEvent));
    } catch {
      // API may not be running
    }
  }, []);

  useEffect(() => {
    loadReminders();
    loadSuggestedEvents();
  }, [loadReminders, loadSuggestedEvents]);

  const resetForm = () => {
    setFormKind("custom");
    setFormMessage("");
    setFormFreq("daily");
    setFormTime("09:00");
    setFormWeekday(0);
    setFormDate("");
    setEditingId(null);
    setShowReminderForm(false);
  };

  const handleSubmit = async () => {
    if (editingId) {
      await updateReminder(editingId, {
        kind: formKind,
        message: formMessage,
        schedule: {
          freq: formFreq,
          time: formTime,
          weekday: formFreq === "weekly" ? formWeekday : null,
          date: formFreq === "once" ? formDate : null,
          timezone: LOCAL_TIMEZONE,
        },
      });
      showToast("Reminder updated");
    } else {
      const body: ReminderCreate = {
        case_id: caseId,
        kind: formKind,
        message: formMessage,
        schedule: {
          freq: formFreq,
          time: formTime,
          weekday: formFreq === "weekly" ? formWeekday : undefined,
          date: formFreq === "once" ? formDate : undefined,
          timezone: LOCAL_TIMEZONE,
        },
      };
      await createReminder(body);
      showToast("Reminder created");
    }
    resetForm();
    await loadReminders();
  };

  const handleEdit = (r: Reminder) => {
    setEditingId(r.id);
    setFormKind(r.kind);
    setFormMessage(r.message);
    setFormFreq(r.schedule.freq);
    setFormTime(r.schedule.time);
    setFormWeekday(r.schedule.weekday ?? 0);
    setFormDate(r.schedule.date ?? "");
    setShowReminderForm(true);
  };

  const handleDelete = async (id: string) => {
    await deleteReminder(id);
    showToast("Reminder deleted");
    await loadReminders();
  };

  const handleToggle = async (r: Reminder) => {
    await updateReminder(r.id, { active: !r.active });
    showToast(r.active ? "Reminder paused" : "Reminder activated");
    await loadReminders();
  };

  const formatNextRun = (iso: string | null | undefined) => {
    if (!iso) return "N/A";
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  // Combine all events for the calendar grid
  const allSuggested = apiSuggested;
  const allEvents = [...events, ...allSuggested];

  const handleDismissSuggested = async (e: CalEvent) => {
    if (e.id) {
      try {
        await deleteSuggestedEvent(e.id);
        await loadSuggestedEvents();
      } catch {
        // ignore
      }
    }
  };

  return (
    <div className="space-y-8">
      {/* Toast */}
      {toast && (
        <div className="fixed right-4 top-4 z-50 rounded-lg border bg-card px-4 py-2 text-sm shadow-lg">
          {toast}
        </div>
      )}

      {/* Header */}
      <div className="space-y-6">
        <div className="space-y-3">
          <h1 className="text-4xl font-bold">Care Calendar</h1>
          <p className="max-w-xl text-sm text-muted-foreground">
            Email scanning will surface care appointments and deadlines here.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button className="px-10 hover:font-bold">+ Appointment</Button>
          <Button className="px-10 hover:font-bold">+ Visit</Button>
          <Button className="px-10 hover:font-bold">+ Deadline</Button>
          <Button
            className="px-10 hover:font-bold"
            onClick={() => {
              resetForm();
              setShowReminderForm(true);
            }}
          >
            + Reminder
          </Button>


        </div>
      </div>

      <MailboxConnections />

      {/* Reminder creation / edit form */}
      {showReminderForm && (
        <Card>
          <CardHeader>
            <CardTitle>{editingId ? "Edit Reminder" : "New Reminder"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <Label>Type</Label>
              <div className="flex gap-2">
                {(Object.keys(KIND_LABELS) as ReminderKind[]).map((k) => (
                  <Button
                    key={k}
                    variant={formKind === k ? "default" : "outline"}
                    size="sm"
                    onClick={() => setFormKind(k)}
                  >
                    {KIND_LABELS[k]}
                  </Button>
                ))}
              </div>
            </div>

            {formKind !== "daily_care_log" && (
              <div className="space-y-1">
                <Label htmlFor="msg">Message</Label>
                <Input
                  id="msg"
                  value={formMessage}
                  onChange={(e) =>setFormMessage(e.target.value)}
                  placeholder="Reminder details"
                />
              </div>
            )}
            {formKind === "daily_care_log" && (
              <p className="text-sm text-muted-foreground">
                A saved reminder to record daily care. Automatic text check-ins are unavailable.
              </p>
            )}

            <div className="flex flex-wrap gap-4">
              <div className="space-y-1">
                <Label>Frequency</Label>
                <div className="flex gap-2">
                  {(["daily", "weekly", "once"] as ScheduleFreq[]).map((f) => (
                    <Button
                      key={f}
                      variant={formFreq === f ? "default" : "outline"}
                      size="sm"
                      onClick={() => setFormFreq(f)}
                    >
                      {FREQ_LABELS[f]}
                    </Button>
                  ))}
                </div>
              </div>

              <div className="space-y-1">
                <Label htmlFor="time">Time (your local time)</Label>
                <Input
                  id="time"
                  type="time"
                  value={formTime}
                  onChange={(e) =>setFormTime(e.target.value)}
                  className="w-32"
                />
              </div>

              {formFreq === "weekly" && (
                <div className="space-y-1">
                  <Label>Day</Label>
                  <div className="flex gap-1">
                    {WEEKDAY_LABELS.map((d, i) => (
                      <Button
                        key={d}
                        variant={formWeekday === i ? "default" : "outline"}
                        size="sm"
                        onClick={() => setFormWeekday(i)}
                      >
                        {d}
                      </Button>
                    ))}
                  </div>
                </div>
              )}

              {formFreq === "once" && (
                <div className="space-y-1">
                  <Label htmlFor="date">Date</Label>
                  <Input
                    id="date"
                    type="date"
                    value={formDate}
                    onChange={(e) =>setFormDate(e.target.value)}
                    className="w-40"
                  />
                </div>
              )}
            </div>

            <div className="flex gap-2">
              <Button onClick={handleSubmit}>
                {editingId ? "Update" : "Create"}
              </Button>
              <Button variant="outline" onClick={resetForm}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Suggested Events panel */}
      <div className="rounded-xl border border-brand-subtle bg-brand-subtle/30 p-4 space-y-3">
          <div className="flex items-center gap-2 text-primary">
            <Sparkles className="size-4" />
            <h3 className="text-sm font-semibold">Suggested Events</h3>
          </div>
          <p className="text-xs text-muted-foreground">
            {allSuggested.length > 0
              ? "Previously saved suggestions. New email scanning is coming soon."
              : "No suggested events yet. Outlook and Gmail connections are coming soon."}
          </p>
          <div className="space-y-2">
            {allSuggested.map((e, idx) => (
              <div
                key={e.id ?? `suggested-${idx}`}
                className="flex items-start justify-between rounded-lg border border-dashed border-primary/30 bg-card px-3 py-2.5"
              >
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="text-sm font-medium text-foreground">{e.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatEventDate(e) || "Date needs review"}{e.time ? ` \u00b7 ${e.time}` : ""}{" \u00b7 "}{e.kind}
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
                    onClick={() => handleDismissSuggested(e)}
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
      </div>

      {/* Month-view calendar grid */}
      <div className="overflow-hidden rounded-xl border border-brand-subtle bg-card shadow-xs">
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
              ? allEvents.filter((e) => e.day === cell.day && isInDisplayedMonth(e))
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
                      title={e.time ? `${e.title} \u00b7 ${e.time}` : e.title}
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

      {/* Active reminders */}
      {!loading && reminders.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-primary">
            <CalendarDays className="size-4" />
            <h3 className="text-sm font-semibold">Saved Reminders</h3>
          </div>
          <p className="text-xs text-muted-foreground">Reminders are saved only. Automatic delivery is unavailable.</p>
          {reminders.map((r) => (
            <Card key={r.id}>
              <CardHeader className="flex flex-row items-center justify-between py-4">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base">
                    {KIND_LABELS[r.kind]}
                  </CardTitle>
                  <Badge variant={r.active ? "default" : "secondary"}>
                    {r.active ? "Active" : "Paused"}
                  </Badge>
                  <Badge variant="outline">
                    {FREQ_LABELS[r.schedule.freq]}
                    {r.schedule.freq === "weekly" && r.schedule.weekday != null
                      ? ` (${WEEKDAY_LABELS[r.schedule.weekday]})`
                      : ""}
                    {" at "}
                    {r.schedule.time}
                  </Badge>
                </div>
                <div className="flex gap-1">
                  <Button variant="outline" size="sm" onClick={() => handleEdit(r)}>
                    Edit
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => handleToggle(r)}>
                    {r.active ? "Pause" : "Resume"}
                  </Button>
                  <Button variant="destructive" size="sm" onClick={() => handleDelete(r.id)}>
                    Delete
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-1 py-0 pb-4">
                <p className="text-sm">
                  {r.kind === "daily_care_log" && !r.message
                    ? "Built-in care-log prompt (hours, meals, meds, mood)"
                    : r.message || "No message"}
                </p>
                <div className="flex gap-4 text-xs text-muted-foreground">
                  <span>Next: {formatNextRun(r.next_run)}</span>
                  {r.last_sent_at && (
                    <span>Last sent: {formatNextRun(r.last_sent_at)}</span>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
