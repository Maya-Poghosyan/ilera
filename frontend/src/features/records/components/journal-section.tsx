"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { createJournal, deleteJournalEntry, reviewIncident, updateJournal } from "@/features/records/api";
import { formatDate, INCIDENT_BADGE } from "@/features/records/format";
import type { JournalEntry } from "@/features/records/types";
import type { Records } from "@/features/records/use-records";

type Draft = { id: string | null; date: string; text: string };

export function JournalSection({ records }: { records: Records }) {
  const { caseId, journal, loading, loadError, run, reload, setSaveError } = records;
  const [draft, setDraft] = useState<Draft | null>(null);

  const save = () => run(async () => {
    if (!caseId || !draft) return;
    if (!draft.date || !draft.text.trim()) { setSaveError("Enter a date and a journal note."); return; }
    const body = { case_id: caseId, date: draft.date, text: draft.text };
    if (draft.id) await updateJournal(draft.id, body);
    else await createJournal(body);
    setDraft(null);
    await reload();
  });

  const remove = (j: JournalEntry) => run(async () => {
    if (!caseId || !window.confirm("Delete this journal entry? This cannot be undone.")) return;
    await deleteJournalEntry(j.id, caseId);
    await reload();
  });

  const review = (j: JournalEntry, status: JournalEntry["incident_status"]) => run(async () => {
    if (!caseId) return;
    await reviewIncident(j.id, caseId, status);
    await reload();
  });

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-xl">Care journal</h2>
        <Button size="sm" variant="outline" onClick={() => setDraft({ id: null, date: "", text: "" })}>+ Entry</Button>
      </div>

      {draft && (
        <Card>
          <CardContent className="space-y-3 py-4">
            <div className="space-y-1">
              <Label htmlFor="jn-date">Date</Label>
              <Input id="jn-date" type="date" value={draft.date} onChange={(e) => setDraft({ ...draft, date: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="jn-text">Entry</Label>
              <Textarea id="jn-text" value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })}
                        placeholder="How was today's care?" rows={3} maxLength={20000} />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={save}>{draft.id ? "Save changes" : "Add"}</Button>
              <Button size="sm" variant="outline" onClick={() => setDraft(null)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && <p className="text-sm text-muted-foreground">Loading...</p>}

      {journal.map((j) => (
        <Card key={j.id} className={j.fall_flagged && j.incident_status !== "dismissed" ? "border-amber-300" : ""}>
          <CardContent className="px-4 py-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-base font-semibold">{formatDate(j.date)}</span>
                {j.fall_flagged && (
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${INCIDENT_BADGE[j.incident_status].className}`}>
                    {INCIDENT_BADGE[j.incident_status].label}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <Button size="sm" variant="ghost" onClick={() => setDraft({ id: j.id, date: j.date, text: j.text })}>Edit</Button>
                <button onClick={() => remove(j)} className="text-muted-foreground hover:text-destructive" aria-label={`Delete journal entry for ${formatDate(j.date)}`}>
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </div>
            <p className="text-sm whitespace-pre-wrap text-muted-foreground">{j.text}</p>
            {j.fall_flagged && (
              <div className="flex flex-wrap items-center gap-2">
                {j.incident_status !== "confirmed" && <Button size="sm" variant="outline" onClick={() => review(j, "confirmed")}>Confirm fall</Button>}
                {j.incident_status !== "dismissed" && <Button size="sm" variant="outline" onClick={() => review(j, "dismissed")}>Not a fall</Button>}
                {j.incident_status !== "unreviewed" && <Button size="sm" variant="ghost" onClick={() => review(j, "unreviewed")}>Reset</Button>}
              </div>
            )}
          </CardContent>
        </Card>
      ))}

      {!loading && !loadError && journal.length === 0 && (
        <p className="text-sm text-muted-foreground">No journal entries for these dates.</p>
      )}
    </section>
  );
}
