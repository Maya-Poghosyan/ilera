import { Check, Sparkles, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { SuggestedEventAPI } from "@/features/calendar/api";

function formatISODate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
}

export function SuggestionsPanel({ pending, loading, failed, onRetry, onReview }: {
  pending: SuggestedEventAPI[];
  loading: boolean;
  failed: boolean;
  onRetry: () => void;
  onReview: (s: SuggestedEventAPI, decision: "accepted" | "dismissed") => void;
}) {
  return (
    <div className="rounded-xl border border-brand-subtle bg-brand-subtle/30 p-4 space-y-3">
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
            {pending.map((e) => (
              <div key={e.id} className="flex items-start justify-between rounded-lg border border-dashed border-primary/30 bg-card px-3 py-2.5">
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-foreground">{e.title}</p>
                    {typeof e.confidence === "number" && (
                      <Badge variant="outline" className="text-[10px]">{Math.round(e.confidence * 100)}% confidence</Badge>
                    )}
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
                  {e.description && (
                    <p className="text-xs leading-relaxed text-muted-foreground/80">{e.description}</p>
                  )}
                </div>
                <div className="ml-3 flex shrink-0 items-center gap-1 pt-0.5">
                  <button
                    className="flex size-7 items-center justify-center rounded-full bg-brand-subtle text-primary hover:bg-primary hover:text-white transition-colors disabled:opacity-40"
                    aria-label="Accept"
                    title={e.date ? "Add to calendar" : "Needs a date before it can be added"}
                    disabled={!e.date}
                    onClick={() => onReview(e, "accepted")}
                  >
                    <Check className="size-3.5" />
                  </button>
                  <button
                    className="flex size-7 items-center justify-center rounded-full bg-brand-subtle text-muted-foreground hover:bg-red-100 hover:text-red-600 transition-colors"
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
    </div>
  );
}
