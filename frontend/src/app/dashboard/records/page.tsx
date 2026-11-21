"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCaseId } from "@/features/accounts/auth-context";
import { JournalSection } from "@/features/records/components/journal-section";
import { RenewalsSection } from "@/features/records/components/renewals-section";
import { TimesheetsSection } from "@/features/records/components/timesheets-section";
import { useRecords } from "@/features/records/use-records";

export default function RecordsPage() {
  const records = useRecords(useCaseId());
  const { caseId, loading, loadError, saveError, pending, reload, fromDate, toDate, setFromDate, setToDate } = records;

  if (!caseId && !loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-4xl">Records &amp; Renewal</h1>
        <Card>
          <CardContent className="py-6">
            <p className="text-sm text-muted-foreground">
              Complete the intake wizard first to create a case profile, then return here to track
              timesheets, journal entries, and renewals.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const hours = records.timekeeping.reduce((total, entry) => total + entry.hours, 0);
  return (
    <div className="space-y-6">
      <fieldset disabled={pending || loading || loadError} className="space-y-6 min-w-0">
        <h1 className="text-4xl">Records &amp; Renewal</h1>

        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-1"><Label htmlFor="records-from">From</Label><Input id="records-from" type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} /></div>
          <div className="space-y-1"><Label htmlFor="records-to">Through</Label><Input id="records-to" type="date" min={fromDate} value={toDate} onChange={(e) => setToDate(e.target.value)} /></div>
          <Button variant="outline" onClick={() => { setFromDate(""); setToDate(""); }}>All dates</Button>
          <p className="text-sm" aria-live="polite">{hours.toFixed(2)} hours · {records.journal.length} journal entries</p>
        </div>
        {fromDate && toDate && fromDate > toDate && <p role="alert">The end date must be on or after the start date.</p>}

        {records.flaggedFalls > 0 && (
          <Card className="border-amber-300 bg-amber-50">
            <CardContent className="flex items-start gap-3 py-4 text-sm">
              <span aria-hidden>🚩</span>
              <p>
                {records.flaggedFalls} journal {records.flaggedFalls === 1 ? "entry mentions" : "entries mention"} a possible fall. Review the highlighted entries below to confirm or dismiss each flag.
              </p>
            </CardContent>
          </Card>
        )}

        <RenewalsSection records={records} />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <TimesheetsSection records={records} />
          <JournalSection records={records} />
        </div>
      </fieldset>
      {loadError && <div role="alert" className="rounded-md border border-destructive p-4">Could not load records. Existing data may be out of date. <Button variant="outline" onClick={() => void reload()}>Retry</Button></div>}
      {saveError && <p role="alert" className="text-destructive">{saveError}</p>}
      {pending && <p role="status">Saving changes…</p>}
    </div>
  );
}
