"use client";

import { useState } from "react";
import { ExternalLink, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createTimekeeping, deleteTimekeepingEntry, updateTimekeeping } from "@/features/records/api";
import { formatDate, SERVICE_LABELS } from "@/features/records/format";
import type { ServiceType, TimekeepingEntry } from "@/features/records/types";
import type { Records } from "@/features/records/use-records";

type Draft = { id: string | null; date: string; hours: string; start: string; end: string; service: ServiceType; tasks: string; notes: string };
const BLANK: Draft = { id: null, date: "", hours: "", start: "", end: "", service: "personal_care", tasks: "", notes: "" };
const minutes = (value: string) => { const [h, m] = value.split(":").map(Number); return h * 60 + m; };

export function TimesheetsSection({ records }: { records: Records }) {
  const { caseId, timekeeping, loading, loadError, run, reload, setSaveError } = records;
  const [draft, setDraft] = useState<Draft | null>(null);
  const change = (patch: Partial<Draft>) => setDraft((d) => (d ? { ...d, ...patch } : d));

  const edit = (e: TimekeepingEntry) => setDraft({
    id: e.id, date: e.date, hours: String(e.hours), start: e.start_time ?? "", end: e.end_time ?? "",
    service: e.service_type, tasks: e.tasks.join(", "), notes: e.notes,
  });

  const save = () => run(async () => {
    if (!caseId || !draft) return;
    const hours = Number(draft.hours);
    if (!draft.date || !Number.isFinite(hours) || hours <= 0 || hours > 24) {
      setSaveError("Enter a date and hours greater than 0 and at most 24."); return;
    }
    if (Boolean(draft.start) !== Boolean(draft.end) || (draft.start && draft.end &&
        (minutes(draft.end) <= minutes(draft.start) || Math.abs(hours * 60 - (minutes(draft.end) - minutes(draft.start))) > 0.01))) {
      setSaveError("Provide both times and matching hours. Split overnight care into separate dates."); return;
    }
    const body = {
      case_id: caseId, date: draft.date, hours, start_time: draft.start || undefined, end_time: draft.end || undefined,
      service_type: draft.service, tasks: draft.tasks.split(",").map((t) => t.trim()).filter(Boolean),
      notes: draft.notes || undefined,
    };
    if (draft.id) await updateTimekeeping(draft.id, body);
    else await createTimekeeping(body);
    setDraft(null);
    await reload();
  });

  const remove = (e: TimekeepingEntry) => run(async () => {
    if (!caseId || !window.confirm("Delete this timesheet entry? This cannot be undone.")) return;
    await deleteTimekeepingEntry(e.id, caseId);
    await reload();
  });

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h2 className="text-xl">Timesheets</h2>
          <a href="https://www.etimesheets.ihss.ca.gov" target="_blank" rel="noopener noreferrer"
             className="inline-flex items-center gap-1 text-sm text-black underline hover:text-black/70">
            Submit timesheet to IHSS portal
            <ExternalLink className="size-3.5" />
          </a>
        </div>
        <Button size="sm" variant="outline" onClick={() => setDraft(BLANK)}>+ Entry</Button>
      </div>

      {draft && (
        <Card>
          <CardContent className="space-y-3 py-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="tk-date">Date</Label>
                <Input id="tk-date" type="date" value={draft.date} onChange={(e) => change({ date: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="tk-hours">Total Hours</Label>
                <Input id="tk-hours" type="number" step="0.25" min="0" max="24" value={draft.hours} onChange={(e) => change({ hours: e.target.value })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="tk-start">Start Time</Label>
                <Input id="tk-start" type="time" value={draft.start} onChange={(e) => change({ start: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="tk-end">End Time</Label>
                <Input id="tk-end" type="time" value={draft.end} onChange={(e) => change({ end: e.target.value })} />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Service Type</Label>
              <div className="flex flex-wrap gap-1.5">
                {(Object.keys(SERVICE_LABELS) as ServiceType[]).map((st) => (
                  <Button key={st} type="button" variant={draft.service === st ? "default" : "outline"} size="sm" onClick={() => change({ service: st })}>
                    {SERVICE_LABELS[st]}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="tk-tasks">Activities (comma-separated)</Label>
              <Input id="tk-tasks" value={draft.tasks} onChange={(e) => change({ tasks: e.target.value })} placeholder="Bathing, dressing, meal prep, medication" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="tk-notes">Notes</Label>
              <Input id="tk-notes" value={draft.notes} onChange={(e) => change({ notes: e.target.value })} placeholder="Any additional details" />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={save}>{draft.id ? "Save changes" : "Add"}</Button>
              <Button size="sm" variant="outline" onClick={() => setDraft(null)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && <p className="text-sm text-muted-foreground">Loading...</p>}

      {timekeeping.map((t) => (
        <Card key={t.id}>
          <CardContent className="px-4 py-3 space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-base font-semibold">{formatDate(t.date)}</span>
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium">{t.hours} {t.hours === 1 ? "hr" : "hrs"}</span>
                {t.start_time && t.end_time && <span className="text-xs text-muted-foreground">{t.start_time}–{t.end_time}</span>}
              </div>
              <div className="flex items-center gap-1">
                <Button size="sm" variant="ghost" onClick={() => edit(t)}>Edit</Button>
                <button onClick={() => remove(t)} className="text-muted-foreground hover:text-destructive" aria-label={`Delete timesheet entry for ${formatDate(t.date)}`}>
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="rounded-full border px-2 py-0.5 text-xs font-medium">{SERVICE_LABELS[t.service_type] ?? t.service_type}</span>
              {t.tasks.map((task) => (
                <span key={task} className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{task}</span>
              ))}
            </div>
            {t.notes && <p className="text-xs text-muted-foreground">{t.notes}</p>}
          </CardContent>
        </Card>
      ))}

      {!loading && !loadError && timekeeping.length === 0 && (
        <p className="text-sm text-muted-foreground">No timesheet entries for these dates.</p>
      )}
    </section>
  );
}
