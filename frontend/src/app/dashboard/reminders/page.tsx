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
  sendTestMessage,
  updateReminder,
} from "@/lib/api";
import type {
  Reminder,
  ReminderCreate,
  ReminderKind,
  ScheduleFreq,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Constants
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

export default function RemindersPage() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // Create form state
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formKind, setFormKind] = useState<ReminderKind>("custom");
  const [formMessage, setFormMessage] = useState("");
  const [formFreq, setFormFreq] = useState<ScheduleFreq>("daily");
  const [formTime, setFormTime] = useState("09:00");
  const [formWeekday, setFormWeekday] = useState(0);
  const [formDate, setFormDate] = useState("");

  // Test message
  const [testMsg, setTestMsg] = useState("");
  const [testSending, setTestSending] = useState(false);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }, []);

  const load = useCallback(async () => {
    try {
      const data = await listReminders();
      setReminders(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load reminders");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resetForm = () => {
    setFormKind("custom");
    setFormMessage("");
    setFormFreq("daily");
    setFormTime("09:00");
    setFormWeekday(0);
    setFormDate("");
    setEditingId(null);
    setShowCreate(false);
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
    await load();
  };

  const handleEdit = (r: Reminder) => {
    setEditingId(r.id);
    setFormKind(r.kind);
    setFormMessage(r.message);
    setFormFreq(r.schedule.freq);
    setFormTime(r.schedule.time);
    setFormWeekday(r.schedule.weekday ?? 0);
    setFormDate(r.schedule.date ?? "");
    setShowCreate(true);
  };

  const handleDelete = async (id: string) => {
    await deleteReminder(id);
    showToast("Reminder deleted");
    await load();
  };

  const handleToggle = async (r: Reminder) => {
    await updateReminder(r.id, { active: !r.active });
    showToast(r.active ? "Reminder paused" : "Reminder activated");
    await load();
  };

  const handleRunNow = async (id: string) => {
    try {
      await runReminderNow(id);
      showToast("Reminder sent via Poke");
      await load();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Send failed");
    }
  };

  const handleTestSend = async () => {
    if (!testMsg.trim()) return;
    setTestSending(true);
    try {
      await sendTestMessage(testMsg);
      showToast("Test message sent via Poke");
      setTestMsg("");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Send failed");
    } finally {
      setTestSending(false);
    }
  };

  const enableDailyCareLog = async () => {
    await createReminder({
      kind: "daily_care_log",
      message: "",
      schedule: { freq: "daily", time: "18:00" },
    });
    showToast("Daily care-log check-in enabled");
    await load();
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

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading reminders...</p>;
  }
  if (error) {
    return <p className="text-sm text-destructive">{error}</p>;
  }

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
          <h1 className="text-2xl font-bold">Reminders</h1>
          <p className="text-sm text-muted-foreground">
            Schedule recurring and one-off reminders delivered via Poke.
          </p>
        </div>
        <div className="flex gap-2">
          {!hasCareLog && (
            <Button variant="outline" size="sm" onClick={enableDailyCareLog}>
              Enable Daily Care Log
            </Button>
          )}
          <Button
            size="sm"
            onClick={() => {
              resetForm();
              setShowCreate(true);
            }}
          >
            + New Reminder
          </Button>
        </div>
      </div>

      {/* Create / Edit form */}
      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle>{editingId ? "Edit Reminder" : "New Reminder"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Kind */}
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

            {/* Message */}
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
                Uses the built-in care-log prompt asking about hours, meals, meds, mood & incidents.
              </p>
            )}

            {/* Schedule */}
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

      {/* Test message */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Send Test Message via Poke</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Input
            value={testMsg}
            onChange={(e) => setTestMsg(e.target.value)}
            placeholder="Type a test message..."
            className="flex-1"
          />
          <Button
            size="sm"
            variant="outline"
            onClick={handleTestSend}
            disabled={testSending || !testMsg.trim()}
          >
            {testSending ? "Sending..." : "Send"}
          </Button>
        </CardContent>
      </Card>

      {/* Reminders list */}
      {reminders.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No reminders yet. Create one or enable the daily care-log check-in.
        </p>
      ) : (
        <div className="space-y-3">
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
