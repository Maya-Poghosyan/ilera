"use client";

import { Check, Pencil, Sparkles, TriangleAlert, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { SuggestedEventAPI, SuggestionEdits } from "@/features/calendar/api";
import { zoneSuffix } from "@/features/calendar/timezone";

function formatISODate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
}

const iconButton = "flex size-9 items-center justify-center rounded-full bg-brand-subtle transition-colors disabled:opacity-40";
// A reviewed suggestion fades (and, when dismissed, slides) out while its space collapses; the
// decision is sent once the motion ends, so the list never jumps.
const EXIT_MS = 280;
type Decision = "accepted" | "dismissed";

/** The caregiver's corrections to one suggestion, made before accepting it. */
function SuggestionEditor({ suggestion, onSave, onCancel }: {
  suggestion: SuggestedEventAPI;
  onSave: (edits: SuggestionEdits) => Promise<boolean>;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(suggestion.title);
  const [date, setDate] = useState(suggestion.date ?? "");
  const [time, setTime] = useState(suggestion.time ?? "");
  const [saving, setSaving] = useState(false);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    const saved = await onSave({ title: title.trim(), ...(date ? { date } : {}), time: time || null });
    if (!saved) setSaving(false);
  }

  return (
    <form onSubmit={save} className="space-y-2 rounded-lg border border-primary/30 bg-card px-3 py-3" aria-label={`Edit ${suggestion.title}`}>
      <label className="block space-y-1 text-xs text-muted-foreground">
        <span>Title</span>
        <Input value={title} maxLength={120} required onChange={(e) => setTitle(e.target.value)} />
      </label>
      <div className="flex flex-wrap gap-2">
        <label className="space-y-1 text-xs text-muted-foreground">
          <span>Date</span>
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="space-y-1 text-xs text-muted-foreground">
          <span>Time (optional)</span>
          <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
        </label>
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={saving || !title.trim()}>Save</Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}

export function SuggestionsPanel({ pending, arrived, timezone, loading, failed, onRetry, onReview, onEdit }: {
  pending: SuggestedEventAPI[];
  /** The calendar's zone; a suggestion in another zone shows its zone's name. */
  timezone: string | null;
  /** Suggestions that just arrived; they animate in once. */
  arrived: ReadonlySet<string>;
  loading: boolean;
  failed: boolean;
  onRetry: () => void;
  onReview: (s: SuggestedEventAPI, decision: Decision) => Promise<boolean>;
  onEdit: (s: SuggestedEventAPI, edits: SuggestionEdits) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [leaving, setLeaving] = useState<Record<string, Decision>>({});

  function decide(e: SuggestedEventAPI, decision: Decision) {
    setLeaving((prev) => ({ ...prev, [e.id]: decision }));
    const wait = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : EXIT_MS;
    setTimeout(async () => {
      // Saved: the reload has already removed it from the list. Not saved: it comes back.
      await onReview(e, decision);
      setLeaving((prev) => {
        const next = { ...prev };
        delete next[e.id];
        return next;
      });
    }, wait);
  }
  // Suggestions with a date can go straight onto the calendar.
  const ready = pending.filter((e) => e.date && !leaving[e.id]);
  return (
    <section aria-label="Suggested events" className="rounded-xl border border-brand-subtle bg-card p-5 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-primary">
          <Sparkles className="size-5" />
          <h3 className="text-2xl">Suggested Events</h3>
        </div>
        {!failed && !loading && ready.length > 1 && (
          <Button variant="outline" size="sm" disabled={ready.some((e) => leaving[e.id])}
            onClick={() => ready.forEach((e) => decide(e, "accepted"))}>
            <Check aria-hidden="true" /> Add all ({ready.length})
          </Button>
        )}
      </div>
      {failed ? (
        <div className="flex items-center justify-between rounded-lg border border-dashed border-red-300 bg-card px-3 py-2.5">
          <p className="text-xs text-red-600">
            Couldn&apos;t load suggestions. This doesn&apos;t mean your mailbox failed to scan.
          </p>
          <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
        </div>
      ) : loading ? (
        <p className="text-sm text-muted-foreground">Loading suggestions&hellip;</p>
      ) : (
        <>
          {pending.length === 0 && <p className="text-sm text-muted-foreground">No suggestions to review.</p>}
          <div>
            {pending.map((e) => editing === e.id ? (
              <div key={e.id} className="pb-2">
              <SuggestionEditor suggestion={e} onCancel={() => setEditing(null)}
                onSave={async (edits) => {
                  const saved = await onEdit(e, edits);
                  if (saved) setEditing(null);
                  return saved;
                }} />
              </div>
            ) : (
              <div key={e.id} data-leaving={leaving[e.id]}
                className={`grid transition-[grid-template-rows,opacity] duration-300 ease-out motion-reduce:transition-none ${leaving[e.id] ? "grid-rows-[0fr] opacity-0" : "grid-rows-[1fr] opacity-100"}`}>
              <div className={`min-h-0 ${leaving[e.id] ? "overflow-hidden" : ""}`}>
              <div className="pb-2">
              <div data-arrived={arrived.has(e.id) || undefined}
                className={`flex items-start gap-4 rounded-lg border border-dashed border-primary/30 bg-card px-4 py-3 transition-transform duration-300 ease-out motion-reduce:transition-none ${leaving[e.id] === "dismissed" ? "-translate-x-6" : ""} ${arrived.has(e.id) ? "motion-safe:animate-suggestion-arrive" : ""}`}>
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="text-base font-medium text-foreground">{e.title}</p>
                  <p className="flex flex-wrap items-center gap-x-1.5 text-sm text-muted-foreground">
                    <span>{e.date ? <>{formatISODate(e.date)}{e.time && `, ${e.time}${zoneSuffix(e.timezone, e.date, timezone)}`}</> : "Date unknown"}</span>
                    <span aria-hidden="true">•</span>
                    <span>{e.kind}</span>
                    {!e.date && <>
                      <span aria-hidden="true">•</span>
                      <span className="flex items-center gap-1 text-foreground"><TriangleAlert aria-hidden="true" className="size-3.5 text-muted-foreground" />Missing: date</span>
                    </>}
                  </p>
                  {e.action_required && (
                    <p className="text-sm text-foreground">Action needed: {e.action_required}</p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <button
                    className={`${iconButton} text-muted-foreground hover:bg-primary hover:text-white`}
                    aria-label={`Edit ${e.title}`}
                    title="Edit"
                    disabled={!!leaving[e.id]}
                    onClick={() => setEditing(e.id)}
                  >
                    <Pencil className="size-4" />
                  </button>
                  <button
                    className={`${iconButton} text-primary hover:bg-primary hover:text-white`}
                    aria-label="Accept"
                    title={e.date ? "Add to calendar" : "Add a date to accept"}
                    disabled={!!leaving[e.id]}
                    onClick={() => (e.date ? decide(e, "accepted") : setEditing(e.id))}
                  >
                    <Check className="size-4" />
                  </button>
                  <button
                    className={`${iconButton} text-muted-foreground hover:bg-red-100 hover:text-red-600`}
                    aria-label="Dismiss"
                    disabled={!!leaving[e.id]}
                    onClick={() => decide(e, "dismissed")}
                  >
                    <X className="size-4" />
                  </button>
                </div>
              </div>
              </div>
              </div>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
