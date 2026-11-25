"use client";

import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { useCaseId } from "@/features/accounts/auth-context";
import { MonthGrid } from "@/features/calendar/components/month-grid";
import { SuggestionsPanel } from "@/features/calendar/components/suggestions-panel";
import { TimezoneSetting } from "@/features/calendar/components/timezone-setting";
import { useCalendar } from "@/features/calendar/use-calendar";
import { useCalendarTimezone } from "@/features/calendar/use-calendar-timezone";
import { MailboxConnections } from "@/features/mailbox/mailbox-connections";
import { ReminderForm } from "@/features/reminders/components/reminder-form";
import { ReminderList } from "@/features/reminders/components/reminder-list";
import { useReminders } from "@/features/reminders/use-reminders";

export default function CalendarPage() {
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
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h1 className="text-4xl">Care Calendar</h1>
            <TimezoneSetting timezone={zone.timezone} source={zone.source} onChange={zone.change} />
          </div>
          <p className="max-w-xl text-sm text-muted-foreground">
            Email scanning will surface care appointments and deadlines here.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button className="px-8">+ Appointment</Button>
          <Button className="px-8">+ Visit</Button>
          <Button className="px-8">+ Deadline</Button>
          <Button className="px-8" onClick={reminders.startNew}>+ Reminder</Button>
        </div>
      </div>

      <MailboxConnections />

      {reminders.draft && (
        <ReminderForm draft={reminders.draft} onChange={reminders.change} onSave={reminders.save} onCancel={reminders.cancel} />
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
        onMonth={calendar.goToMonth}
        onToday={calendar.goToday}
      />

      {!reminders.loading && (
        <ReminderList reminders={reminders.reminders} onEdit={reminders.edit} onToggle={reminders.toggle} onDelete={reminders.remove} />
      )}
    </div>
  );
}
