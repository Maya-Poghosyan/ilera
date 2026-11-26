"use client";

import { AlertCircle, CheckCircle2, FileText, Loader2, Upload, X } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { UploadDocument } from "@/features/intake/schema";
import { questionFor } from "@/features/intake/documents/suggestions";
import type { IntakeDocument } from "@/features/intake/documents/use-intake-documents";

const mb = (bytes: number) => `${Math.round(bytes / 1024 / 1024)} MB`;

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** What a document gave: suggestions for questions ahead, and for questions already passed. */
function status(d: IntakeDocument, passed: ReadonlySet<string>): string {
  if (d.status === "reading") return "Reading…";
  if (d.status === "failed") return d.message;
  if (!d.suggestions.length) return "No answers found in this document. You can enter them yourself.";
  const behind = d.suggestions.filter(s => passed.has(questionFor(s))).length;
  const ahead = d.suggestions.length - behind;
  const back = `for ${behind === 1 ? "a question" : "questions"} you've already passed. Use Back to review ${behind === 1 ? "it" : "them"}.`;
  if (!behind) return `${plural(ahead, "suggested answer")} to review in the questions ahead`;
  if (!ahead) return `${plural(behind, "suggested answer")} ${back}`;
  return `${plural(ahead, "suggested answer")} to review in the questions ahead, and ${behind} ${back}`;
}

/** Shown after a section's title card. The collection is shared by every section. */
export function UploadCard({ suggested, limits, documents, passed, onAdd, onRemove }: {
  suggested: UploadDocument[];
  limits: { max_bytes: number; accept: string[] };
  documents: IntakeDocument[];
  /** Questions on pages before this one. */
  passed: ReadonlySet<string>;
  onAdd: (files: File[]) => void;
  onRemove: (id: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const headingId = useId();
  const [error, setError] = useState<string | null>(null);

  function handleFiles(list: FileList | null) {
    const files = [...(list ?? [])];
    const tooLarge = files.filter(f => f.size > limits.max_bytes);
    setError(tooLarge.length ? `${tooLarge.map(f => f.name).join(", ")} ${tooLarge.length === 1 ? "is" : "are"} over ${mb(limits.max_bytes)}.` : null);
    const ok = files.filter(f => f.size <= limits.max_bytes);
    if (ok.length) onAdd(ok);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <Card aria-labelledby={headingId} className="text-base [--card-spacing:--spacing(7)]">
      <CardHeader>
        <CardTitle id={headingId} className="text-lg">Autofill with documents (optional)</CardTitle>
      </CardHeader>
      <CardContent className="-mt-3 space-y-4 text-sm text-muted-foreground">
        <p>We&rsquo;ll read these and suggest answers in the questions ahead. You review every suggestion, and you can always enter answers yourself.</p>
        <ul className="space-y-3">
          {suggested.map(s => <li key={s.document}>
            <p><span className="font-medium text-foreground">{s.document}</span> &mdash; {s.fills}</p>
            <p className="text-xs">From {s.location}{s.cover && <>. Cover {s.cover} first</>}.</p>
          </li>)}
        </ul>
        <input ref={inputRef} type="file" multiple accept={limits.accept.join(",")} className="sr-only" tabIndex={-1}
          aria-label="Document files" onChange={e => handleFiles(e.target.files)} />
        <Button variant="outline" onClick={() => inputRef.current?.click()}>
          <Upload aria-hidden="true" /> Choose files
        </Button>
        <p className="text-xs">PDF, JPG, PNG, up to {mb(limits.max_bytes)}</p>
        {error && <p role="alert" className="text-destructive">{error}</p>}
        {documents.length > 0 && <ul aria-label="Your documents" aria-live="polite" className="divide-y rounded-lg border">
          {documents.map(d => <li key={d.id} className="flex items-start gap-3 px-3 py-2">
            {d.status === "reading" ? <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin" aria-hidden="true" />
              : d.status === "failed" ? <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
              : d.suggestions.length ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
              : <FileText className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
            <div className="min-w-0 flex-1">
              <p className="truncate text-foreground">{d.name}</p>
              <p className={d.status === "failed" ? "text-destructive" : ""}>{status(d, passed)}</p>
            </div>
            <Button variant="ghost" size="icon-sm" aria-label={`Remove ${d.name}`} onClick={() => onRemove(d.id)}>
              <X aria-hidden="true" />
            </Button>
          </li>)}
        </ul>}
      </CardContent>
    </Card>
  );
}
