"use client";

import { FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Answers, AnswerValue } from "@/lib/intake-schema";
import { answerChange, describe, isApplied, otherTaxYear } from "./suggestions";
import type { PendingSuggestion } from "./use-intake-documents";

/** Proposed answers for one question: value, document, page, date. Applied only on confirmation. */
export function SuggestionPanel({ pending, answers, recipientName, onApply, onDismiss }: {
  pending: PendingSuggestion[];
  answers: Answers;
  recipientName: string;
  onApply: (fieldId: string, value: AnswerValue) => void;
  onDismiss: (key: string) => void;
}) {
  const values = pending.flatMap(p => p.suggestion.kind === "answer" ? [JSON.stringify(p.suggestion.value)] : []);
  const conflict = new Set(values).size > 1;
  return (
    <section aria-label="Suggestions from your documents" className="space-y-3 rounded-lg border border-primary/30 bg-secondary/40 p-4 text-sm">
      <p className="font-medium text-foreground">{conflict ? "Your documents disagree. Choose the one that's current, or enter your own answer." : "From your documents. Check it before using it."}</p>
      {pending.map(({ key, documentName, suggestion: s }) => {
        const change = answerChange(s, answers);
        const applied = isApplied(s, answers);
        const year = otherTaxYear(s, answers);
        return (
          <div key={key} className="flex flex-wrap items-start justify-between gap-3 border-t border-primary/20 pt-3 first-of-type:border-0 first-of-type:pt-0">
            <div className="min-w-0 space-y-1">
              <p className="text-base font-semibold text-foreground">{describe(s, recipientName)}</p>
              <p className="flex items-center gap-1.5 text-muted-foreground">
                <FileText className="size-3.5 shrink-0" aria-hidden="true" />
                <span className="truncate">&ldquo;{documentName}&rdquo;, page {s.source.page}{s.source.as_of ? `, ${s.source.as_of}` : ""}</span>
              </p>
              {s.source.evidence && <p className="text-muted-foreground">{s.source.evidence}</p>}
              {year !== null && <p className="text-destructive">This is from {year}, not the tax year you chose.</p>}
              {!change && <p className="text-muted-foreground">Enter this amount on the right household member&rsquo;s card.</p>}
            </div>
            <div className="flex shrink-0 gap-2">
              {applied ? <span role="status" className="self-center text-primary">Answer filled in</span>
                : change && <Button size="sm" onClick={() => onApply(...change)}>Use this answer</Button>}
              <Button size="sm" variant="ghost" onClick={() => onDismiss(key)}>{applied ? "Hide" : "Not right"}</Button>
            </div>
          </div>
        );
      })}
    </section>
  );
}
