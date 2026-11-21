"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { createRenewal, deleteRenewalItem, updateRenewalItem } from "@/features/records/api";
import { formatDate, relativeDue, RENEWAL_STATUSES, STATUS_LABELS, URGENCY_BADGE, URGENCY_ORDER } from "@/features/records/format";
import type { RenewalItem, RenewalStatus } from "@/features/records/types";
import type { Records } from "@/features/records/use-records";

type Draft = { id: string | null; program: string; due: string; status: RenewalStatus; lastCompleted: string; period: string; notes: string };
const BLANK: Draft = { id: null, program: "", due: "", status: "active", lastCompleted: "", period: "", notes: "" };

export function RenewalsSection({ records }: { records: Records }) {
  const { caseId, renewals, loading, loadError, run, reload, setSaveError } = records;
  const [draft, setDraft] = useState<Draft | null>(null);
  const change = (patch: Partial<Draft>) => setDraft((d) => (d ? { ...d, ...patch } : d));

  // Surface the most urgent renewals first, then soonest-due within a bucket.
  const sorted = [...renewals].sort((a, b) =>
    URGENCY_ORDER[a.urgency] - URGENCY_ORDER[b.urgency]
    || (a.due_date && b.due_date ? a.due_date.localeCompare(b.due_date) : a.program.localeCompare(b.program)));
  const overdue = renewals.filter((r) => r.urgency === "overdue").length;
  const dueSoon = renewals.filter((r) => r.urgency === "due_soon").length;

  const edit = (item: RenewalItem) => setDraft({
    id: item.id, program: item.program, due: item.due_date ?? "", status: item.status,
    lastCompleted: item.last_completed_date ?? "",
    period: item.renewal_period_months != null ? String(item.renewal_period_months) : "", notes: item.notes,
  });

  const save = () => run(async () => {
    if (!caseId || !draft) return;
    if (!draft.program.trim()) { setSaveError("Enter the program this renewal is for."); return; }
    const period = draft.period.trim() ? Number(draft.period) : null;
    if (period != null && (!Number.isInteger(period) || period < 1 || period > 120)) {
      setSaveError("Renewal period must be a whole number of months between 1 and 120."); return;
    }
    const body = {
      program: draft.program.trim(), due_date: draft.due || null, status: draft.status,
      last_completed_date: draft.lastCompleted || null, renewal_period_months: period, notes: draft.notes,
    };
    if (draft.id) await updateRenewalItem(draft.id, caseId, body);
    else await createRenewal({ case_id: caseId, ...body });
    setDraft(null);
    await reload();
  });

  const remove = (item: RenewalItem) => run(async () => {
    if (!caseId || !window.confirm("Delete this renewal? This cannot be undone.")) return;
    await deleteRenewalItem(item.id, caseId);
    await reload();
  });

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl">Renewals</h2>
          {overdue > 0 && (
            <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 border border-red-300">{overdue} overdue</span>
          )}
          {dueSoon > 0 && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 border border-amber-300">{dueSoon} due soon</span>
          )}
        </div>
        <Button size="sm" variant="outline" onClick={() => setDraft(BLANK)}>+ Renewal</Button>
      </div>

      {draft && (
        <Card>
          <CardContent className="space-y-3 py-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="rn-program">Program</Label>
                <Input id="rn-program" value={draft.program} onChange={(e) => change({ program: e.target.value })} placeholder="IHSS, Medi-Cal, PFL, VA…" />
              </div>
              <div className="space-y-1">
                <Label htmlFor="rn-due">Due date</Label>
                <Input id="rn-due" type="date" value={draft.due} onChange={(e) => change({ due: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="rn-last">Last completed</Label>
                <Input id="rn-last" type="date" value={draft.lastCompleted} onChange={(e) => change({ lastCompleted: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="rn-period">Renewal period (months)</Label>
                <Input id="rn-period" type="number" min="1" max="120" value={draft.period} onChange={(e) => change({ period: e.target.value })} placeholder="12" />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Status</Label>
              <div className="flex flex-wrap gap-1.5">
                {RENEWAL_STATUSES.map((s) => (
                  <Button key={s} type="button" variant={draft.status === s ? "default" : "outline"} size="sm" onClick={() => change({ status: s })}>
                    {STATUS_LABELS[s]}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="rn-notes">Notes</Label>
              <Textarea id="rn-notes" value={draft.notes} onChange={(e) => change({ notes: e.target.value })} placeholder="Renewal packet details, contacts, what's needed…" rows={2} maxLength={2000} />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={save}>{draft.id ? "Save changes" : "Add"}</Button>
              <Button size="sm" variant="outline" onClick={() => setDraft(null)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {!loading && !loadError && renewals.length === 0 && (
        <p className="text-sm text-muted-foreground">No renewals tracked yet. Add one to keep deadlines in view.</p>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {sorted.map((r) => {
          const badge = URGENCY_BADGE[r.urgency];
          return (
            <Card key={r.id} className={r.urgency === "overdue" ? "border-red-300" : r.urgency === "due_soon" ? "border-amber-300" : ""}>
              <CardContent className="space-y-2 px-4 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-base font-semibold">{r.program}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>{badge.label}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button size="sm" variant="ghost" onClick={() => edit(r)}>Edit</Button>
                    <button onClick={() => remove(r)} className="text-muted-foreground hover:text-destructive" aria-label={`Delete ${r.program} renewal`}>
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
                <p className={`text-sm font-medium ${r.urgency === "overdue" ? "text-red-700" : r.urgency === "due_soon" ? "text-amber-700" : "text-foreground"}`}>
                  {relativeDue(r.due_date)}
                  {r.due_date && <span className="font-normal text-muted-foreground"> · {formatDate(r.due_date)}</span>}
                </p>
                <p className="text-xs text-muted-foreground">
                  Status: {STATUS_LABELS[r.status]}
                  {r.renewal_period_months ? ` · Renews every ${r.renewal_period_months} mo` : ""}
                  {r.last_completed_date ? ` · Last completed ${formatDate(r.last_completed_date)}` : ""}
                </p>
                {r.notes && <p className="text-sm whitespace-pre-wrap">{r.notes}</p>}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
