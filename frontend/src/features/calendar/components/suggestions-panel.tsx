"use client";

import { Check, Pencil, Sparkles, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { SuggestedEventAPI, SuggestionEdits } from "@/features/calendar/api";

function formatISODate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
}

const iconButton = "flex size-7 items-center justify-center rounded-full bg-brand-subtle transition-colors disabled:opacity-40";

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

export function SuggestionsPanel({ pending, loading, failed, onRetry, onReview, onEdit }: {
  pending: SuggestedEventAPI[];
  loading: boolean;
  failed: boolean;
  onRetry: () => void;
  onReview: (s: SuggestedEventAPI, decision: "accepted" | "dismissed") => void;
  onEdit: (s: SuggestedEventAPI, edits: SuggestionEdits) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  return (
    <section aria-label="Suggested events" className="rounded-xl border border-brand-subtle bg-brand-subtle/30 p-4 space-y-3">
      <div className="flex items-center gap-2 text-primary">
        <Sparkles className="size-4" />
        <h3 className="text-sm">Suggested Events</h3>
      </div>
      {failed ? (
        <div className="flex items-center justify-between rounded-lg border border-dashed border-red-300 bg-card px-3 py-2.5">
          <p className="text-xs text-red-600">
            Couldn&apos;t load suggestions. This doesn&apos;t mean your mailbox failed to scan.
          </p>
          <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
        </div>
      ) : loading ? (
        <p className="text-xs text-muted-foreground">Loading suggestions&hellip;</p>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {pending.length > 0
              ? "Detected from your connected mailbox. Review each one before it joins your calendar."
              : "No suggestions to review. New ones appear here after a connected mailbox is scanned."}
          </p>
          <div className="space-y-2">
            {pending.map((e) => editing === e.id ? (
              <SuggestionEditor key={e.id} suggestion={e} onCancel={() => setEditing(null)}
                onSave={async (edits) => {
                  const saved = await onEdit(e, edits);
                  if (saved) setEditing(null);
                  return saved;
                }} />
            ) : (
              <div key={e.id} className="flex items-start justify-between rounded-lg border border-dashed border-primary/30 bg-card px-3 py-2.5">
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-foreground">{e.title}</p>
                    {e.source && (
                      <Badge variant="secondary" className="text-[10px] capitalize">
                        {e.source === "email" ? "From email" : e.source}
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {e.date ? formatISODate(e.date) : "Date needs review"}
                    {e.time ? ` · ${e.time}` : ""}{" · "}
                    {e.kind}
                  </p>
                  {e.action_required && (
                    <p className="text-xs font-medium text-amber-600">Action needed: {e.action_required}</p>
                  )}
                </div>
                <div className="ml-3 flex shrink-0 items-center gap-1 pt-0.5">
                  <button
                    className={`${iconButton} text-muted-foreground hover:bg-primary hover:text-white`}
                    aria-label={`Edit ${e.title}`}
                    title="Edit"
                    onClick={() => setEditing(e.id)}
                  >
                    <Pencil className="size-3.5" />
                  </button>
                  <button
                    className={`${iconButton} text-primary hover:bg-primary hover:text-white`}
                    aria-label="Accept"
                    title={e.date ? "Add to calendar" : "Add a date first (edit)"}
                    disabled={!e.date}
                    onClick={() => onReview(e, "accepted")}
                  >
                    <Check className="size-3.5" />
                  </button>
                  <button
                    className={`${iconButton} text-muted-foreground hover:bg-red-100 hover:text-red-600`}
                    aria-label="Dismiss"
                    onClick={() => onReview(e, "dismissed")}
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
