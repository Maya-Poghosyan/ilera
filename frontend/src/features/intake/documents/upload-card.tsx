"use client";

import { AlertCircle, CheckCircle2, FileText, Loader2, Upload, X } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { UploadDocument } from "@/features/intake/schema";
import type { IntakeDocument } from "@/features/intake/documents/use-intake-documents";

const mb = (bytes: number) => `${Math.round(bytes / 1024 / 1024)} MB`;

function status(d: IntakeDocument): string {
  if (d.status === "reading") return "Reading…";
  if (d.status === "failed") return d.message;
  const n = d.suggestions.length;
  return n ? `${n} suggested answer${n === 1 ? "" : "s"} to review in the questions ahead` : "No answers found in this document. You can enter them yourself.";
}

/** Shown after a section's title card. The collection is shared by every section. */
export function UploadCard({ suggested, limits, documents, onAdd, onRemove }: {
  suggested: UploadDocument[];
  limits: { max_bytes: number; accept: string[] };
  documents: IntakeDocument[];
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
        <CardTitle id={headingId} className="text-lg">Add documents (optional)</CardTitle>
      </CardHeader>
      <CardContent className="-mt-3 space-y-4 text-sm text-muted-foreground">
        <p>We&rsquo;ll read these and suggest answers in the questions ahead. You review every suggestion, and you can always enter answers yourself.</p>
        <ul className="list-disc space-y-1 pl-5">
          {suggested.map(s => <li key={s.document}><span className="text-foreground">{s.document}</span>{s.note && <> &mdash; {s.note}</>}</li>)}
        </ul>
        <input ref={inputRef} type="file" multiple accept={limits.accept.join(",")} className="sr-only" tabIndex={-1}
          aria-label="Document files" onChange={e => handleFiles(e.target.files)} />
        <Button variant="outline" onClick={() => inputRef.current?.click()}>
          <Upload aria-hidden="true" /> Choose files
        </Button>
        <p className="text-xs">PDF, JPG or PNG, up to {mb(limits.max_bytes)} each. Files are read once and not stored. Suggestions stay in this tab until you use them.</p>
        {error && <p role="alert" className="text-destructive">{error}</p>}
        {documents.length > 0 && <ul aria-label="Your documents" aria-live="polite" className="divide-y rounded-lg border">
          {documents.map(d => <li key={d.id} className="flex items-start gap-3 px-3 py-2">
            {d.status === "reading" ? <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin" aria-hidden="true" />
              : d.status === "failed" ? <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
              : d.suggestions.length ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
              : <FileText className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
            <div className="min-w-0 flex-1">
              <p className="truncate text-foreground">{d.name}</p>
              <p className={d.status === "failed" ? "text-destructive" : ""}>{status(d)}</p>
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
