"use client";

import { useCallback, useState } from "react";

import { SidePanel } from "@/components/side-panel";
import { EventForm } from "@/features/calendar/components/event-form";
import { Button } from "@/components/ui/button";
import { useCaseId } from "@/features/accounts/auth-context";
import { MonthGrid } from "@/features/calendar/components/month-grid";
import { SuggestionsPanel } from "@/features/calendar/components/suggestions-panel";
import { TimezoneSetting } from "@/features/calendar/components/timezone-setting";
import { useCalendar, type EventKind } from "@/features/calendar/use-calendar";
import { useCalendarTimezone } from "@/features/calendar/use-calendar-timezone";
import { MailboxConnections } from "@/features/mailbox/mailbox-connections";
import { ReminderForm } from "@/features/reminders/components/reminder-form";
import { ReminderList } from "@/features/reminders/components/reminder-list";
import { useReminders } from "@/features/reminders/use-reminders";

export default function CalendarPage() {
  const [eventKind, setEventKind] = useState<EventKind | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const notify = useCallback((message: string) => {
    setToast(message);
    setTimeout(() => setToast(null), 3000);
  }, []);
  const caseId = useCaseId();
  const calendar = useCalendar(notify);
  const zone = useCalendarTimezone(caseId, notify);
  const reminders = useReminders(caseId, notify);

  return (
    <div className="space-y-8">
      {toast && (
        <div className="fixed right-4 top-4 z-50 rounded-lg border bg-card px-4 py-2 text-sm shadow-lg">{toast}</div>
      )}

      <div className="space-y-6">
        <div className="space-y-3">
          <h1 className="page-title">Care Calendar</h1>
        </div>
        <div className="flex flex-wrap gap-3">
          {(["Appointment", "Visit", "Deadline"] as const).map((kind) => (
            <Button key={kind} className="px-8 font-heading text-base" onClick={() => setEventKind(kind)}>+ {kind}</Button>
          ))}
          <Button className="px-8 font-heading text-base" onClick={reminders.startNew}>+ Reminder</Button>
        </div>
      </div>

      {eventKind && <EventForm kind={eventKind} onClose={() => setEventKind(null)} onSaved={() => {
        setEventKind(null);
        notify("Added to your calendar");
        void calendar.refresh();
      }} />}

      {reminders.draft && (
        <SidePanel title={reminders.draft.id ? "Edit reminder" : "Add reminder"} onClose={reminders.cancel}>
          <ReminderForm draft={reminders.draft} onChange={reminders.change} onSave={reminders.save} onCancel={reminders.cancel} />
        </SidePanel>
      )}

      <SuggestionsPanel
        pending={calendar.pending}
        arrived={calendar.arrived}
        timezone={zone.timezone}
        loading={calendar.loading}
        failed={calendar.failed}
        onRetry={calendar.retry}
        onReview={calendar.review}
        onEdit={calendar.edit}
      />

      <MonthGrid
        year={calendar.viewYear}
        month={calendar.viewMonth}
        cells={calendar.cells}
        events={calendar.events}
        timezone={zone.timezone}
        actions={<TimezoneSetting timezone={zone.timezone} onChange={zone.change} />}
        onMonth={calendar.goToMonth}
        onToday={calendar.goToday}
      />

      <MailboxConnections />

      {!reminders.loading && (
        <ReminderList reminders={reminders.reminders} onEdit={reminders.edit} onToggle={reminders.toggle} onDelete={reminders.remove} />
      )}
    </div>
  );
}
