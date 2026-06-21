"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createReminder,
  deleteReminder,
  listReminders,
  runReminderNow,
  scanForEvents,
  updateReminder,
} from "@/lib/api";
import type {
  Reminder,
  ReminderCreate,
  ReminderKind,
  ScheduleFreq,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Static calendar events (sample data)
// ---------------------------------------------------------------------------

const STATIC_EVENTS = [
  { title: "Dr. Patel \u2014 cardiology follow-up", date: "Mon, Jun 23 \u00b7 10:00 AM", kind: "Appointment" },
  { title: "County social worker visit", date: "Wed, Jun 25 \u00b7 2:00 PM", kind: "Visit" },
  { title: "IHSS timesheet due", date: "Fri, Jun 27", kind: "Deadline" },
];

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
// Suggested event type (from Poke scan)
// ---------------------------------------------------------------------------

interface SuggestedEvent {
  title: string;
  date: string;
  source: string;
  kind: string;
  detected_at: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function CalendarPage() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [suggestedEvents, setSuggestedEvents] = useState<SuggestedEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
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
      const data = await listReminders();
      setReminders(data);
    } catch {
      // API may not be running — show empty state
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReminders();
  }, [loadReminders]);

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
        },
      });
      showToast("Reminder updated");
    } else {
      const body: ReminderCreate = {
        kind: formKind,
        message: formMessage,
        schedule: {
          freq: formFreq,
          time: formTime,
          weekday: formFreq === "weekly" ? formWeekday : undefined,
          date: formFreq === "once" ? formDate : undefined,
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

  const handleRunNow = async (id: string) => {
    try {
      await runReminderNow(id);
      showToast("Reminder sent via Poke");
      await loadReminders();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Send failed");
    }
  };

  const handleScan = async () => {
    setScanning(true);
    try {
      const result = await scanForEvents();
      const now = new Date().toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });

      // Parse Poke response — could be structured JSON or text
      const pokeData = result.poke as Record<string, unknown> | undefined;
      let events: SuggestedEvent[] = [];

      if (pokeData && Array.isArray(pokeData)) {
        events = (pokeData as Array<Record<string, string>>).map((e) => ({
          title: e.title ?? "Untitled event",
          date: e.date ?? "Date TBD",
          source: e.source ?? "",
          kind: e.kind ?? "Other",
          detected_at: now,
        }));
      } else {
        // Poke returned a non-array response; surface it as a single suggestion
        const text =
          typeof pokeData === "object" && pokeData !== null
            ? JSON.stringify(pokeData)
            : String(pokeData ?? "");
        if (text) {
          events = [
            {
              title: "Poke scan result",
              date: "See details",
              source: text.slice(0, 200),
              kind: "Other",
              detected_at: now,
            },
          ];
        }
      }
      setSuggestedEvents((prev) => [...events, ...prev]);
      showToast(`Scan complete \u2014 ${events.length} suggestion(s) found`);
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  };

  const enableDailyCareLog = async () => {
    await createReminder({
      kind: "daily_care_log",
      message: "",
      schedule: { freq: "daily", time: "18:00" },
    });
    showToast("Daily care-log check-in enabled");
    await loadReminders();
  };

  const hasCareLog = reminders.some(
    (r) => r.kind === "daily_care_log" && r.active
  );

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

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toast && (
        <div className="fixed right-4 top-4 z-50 rounded-lg border bg-card px-4 py-2 text-sm shadow-lg">
          {toast}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Care Calendar</h1>
          <p className="text-sm text-muted-foreground">
            Poke scans email &amp; messages for medical events and delivers reminders.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">+ Appointment</Button>
          <Button variant="outline" size="sm">+ Visit</Button>
          <Button variant="outline" size="sm">+ Deadline</Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              resetForm();
              setShowReminderForm(true);
            }}
          >
            + Reminder
          </Button>
          {!hasCareLog && (
            <Button variant="outline" size="sm" onClick={enableDailyCareLog}>
              + Care Log
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleScan}
            disabled={scanning}
          >
            {scanning ? "Scanning..." : "Scan Messages"}
          </Button>
        </div>
      </div>

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
                  onChange={(e) => setFormMessage(e.target.value)}
                  placeholder="Reminder text sent to caregiver"
                />
              </div>
            )}
            {formKind === "daily_care_log" && (
              <p className="text-sm text-muted-foreground">
                Uses the built-in care-log prompt asking about hours, meals, meds, mood &amp; incidents.
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
                <Label htmlFor="time">Time (UTC)</Label>
                <Input
                  id="time"
                  type="time"
                  value={formTime}
                  onChange={(e) => setFormTime(e.target.value)}
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
                    onChange={(e) => setFormDate(e.target.value)}
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

      {/* Suggested events from Poke scan */}
      {suggestedEvents.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Suggested Events</h2>
          {suggestedEvents.map((e, i) => (
            <Card key={`suggested-${i}`} className="border-dashed">
              <CardHeader className="flex flex-row items-center justify-between py-4">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-base">{e.title}</CardTitle>
                  <Badge variant="secondary">{e.kind}</Badge>
                  <Badge variant="outline">Suggested</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-1 py-0 pb-4">
                <p className="text-sm text-muted-foreground">{e.date}</p>
                {e.source && (
                  <p className="text-xs text-muted-foreground italic">
                    &quot;{e.source}&quot;
                  </p>
                )}
                <p className="text-xs text-muted-foreground">
                  Detected on {e.detected_at}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Static calendar events */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold">Upcoming Events</h2>
        {STATIC_EVENTS.map((e) => (
          <Card key={e.title}>
            <CardHeader className="flex flex-row items-center justify-between py-4">
              <CardTitle className="text-base">{e.title}</CardTitle>
              <span className="text-xs text-muted-foreground">{e.kind}</span>
            </CardHeader>
            <CardContent className="py-0 pb-4 text-sm text-muted-foreground">{e.date}</CardContent>
          </Card>
        ))}
      </div>

      {/* Active reminders */}
      {!loading && reminders.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Active Reminders</h2>
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
                  <Button variant="outline" size="sm" onClick={() => handleRunNow(r.id)}>
                    Send Now
                  </Button>
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
