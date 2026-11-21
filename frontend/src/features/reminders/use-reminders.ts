"use client";

import { useCallback, useEffect, useState } from "react";

import { createReminder, deleteReminder, listReminders, updateReminder } from "@/features/reminders/api";
import type { Reminder, ReminderKind, ScheduleFreq } from "@/features/reminders/types";

// Reminder times are wall-clock in the caregiver's own zone, not the server's.
const LOCAL_TIMEZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

export type ReminderDraft = {
  id: string | null; // the reminder being edited, or null for a new one
  kind: ReminderKind;
  message: string;
  freq: ScheduleFreq;
  time: string;
  weekday: number; // 0=Mon … 6=Sun
  date: string;
};

const BLANK: ReminderDraft = { id: null, kind: "custom", message: "", freq: "daily", time: "09:00", weekday: 0, date: "" };

/** A case's saved reminders and the one being created or edited. */
export function useReminders(caseId: string | null, notify: (message: string) => void) {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [loading, setLoading] = useState(caseId !== null);
  const [draft, setDraft] = useState<ReminderDraft | null>(null);

  const load = useCallback(async () => {
    if (!caseId) return;
    try {
      setReminders(await listReminders(caseId));
    } catch {
      notify("Could not load reminders. Please refresh.");
    } finally {
      setLoading(false);
    }
  }, [caseId, notify]);

  useEffect(() => {
    // load() only sets state after its request resolves, so this cannot cascade renders.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const save = async () => {
    if (!draft) return;
    // Only the field the frequency uses is sent; the API rejects the others.
    const schedule = {
      freq: draft.freq,
      time: draft.time,
      weekday: draft.freq === "weekly" ? draft.weekday : null,
      date: draft.freq === "once" ? draft.date : null,
      timezone: LOCAL_TIMEZONE,
    };
    if (draft.id) {
      await updateReminder(draft.id, { kind: draft.kind, message: draft.message, schedule });
      notify("Reminder updated");
    } else if (caseId) {
      await createReminder({ case_id: caseId, kind: draft.kind, message: draft.message, schedule });
      notify("Reminder created");
    }
    setDraft(null);
    await load();
  };

  const edit = (r: Reminder) => setDraft({
    id: r.id, kind: r.kind, message: r.message, freq: r.schedule.freq, time: r.schedule.time,
    weekday: r.schedule.weekday ?? 0, date: r.schedule.date ?? "",
  });

  const remove = async (id: string) => {
    await deleteReminder(id);
    notify("Reminder deleted");
    await load();
  };

  const toggle = async (r: Reminder) => {
    await updateReminder(r.id, { active: !r.active });
    notify(r.active ? "Reminder paused" : "Reminder activated");
    await load();
  };

  return {
    reminders, loading, draft,
    startNew: () => setDraft(BLANK),
    change: (patch: Partial<ReminderDraft>) => setDraft((d) => (d ? { ...d, ...patch } : d)),
    cancel: () => setDraft(null),
    save, edit, remove, toggle,
  };
}
