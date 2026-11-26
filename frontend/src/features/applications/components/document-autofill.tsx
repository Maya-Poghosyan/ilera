"use client";

import { AlertCircle, CheckCircle2, FileText, Loader2, Upload, X } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AppDocument } from "@/features/applications/use-application-flow";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "application/pdf,image/jpeg,image/png";

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

function status(d: AppDocument): string {
  if (d.status === "reading") return "Reading…";
  if (d.status === "failed") return d.message;
  if (!d.filled && !d.kept) return "No answers found in this document. You can enter them yourself.";
  const filled = d.filled ? `Filled in ${plural(d.filled, "answer")}. Check each one as you go.` : "";
  const kept = d.kept ? ` ${plural(d.kept, "answer")} you'd already given ${d.kept === 1 ? "was" : "were"} left as is.` : "";
  return (filled + kept).trim();
}

/** Upload documents to fill in this application's answers. Every filled answer stays editable. */
export function DocumentAutofill({ suggested, documents, onAdd, onRemove }: {
  /** Documents this program asks for, which are the likeliest to hold the answers. */
  suggested: string[];
  documents: AppDocument[];
  onAdd: (files: File[]) => void;
  onRemove: (id: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const headingId = useId();
  const [error, setError] = useState<string | null>(null);

  function handleFiles(list: FileList | null) {
    const files = [...(list ?? [])];
    const tooLarge = files.filter((f) => f.size > MAX_BYTES);
    setError(tooLarge.length ? `${tooLarge.map((f) => f.name).join(", ")} ${tooLarge.length === 1 ? "is" : "are"} over 10 MB.` : null);
    const ok = files.filter((f) => f.size <= MAX_BYTES);
    if (ok.length) onAdd(ok);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <Card aria-labelledby={headingId}>
      <CardHeader>
        <CardTitle id={headingId} className="text-lg">Autofill from documents (optional)</CardTitle>
      </CardHeader>
      <CardContent className="-mt-3 space-y-4 text-sm text-muted-foreground">
        <p>Upload documents and we&rsquo;ll fill in any blank answers they cover. Answers you&rsquo;ve already given are kept. You can change anything we fill in.</p>
        {suggested.length > 0 && (
          <div className="space-y-1.5">
            <p className="font-medium text-foreground">Helpful documents for this application</p>
            <ul className="list-disc space-y-1 pl-5">
              {suggested.map((doc) => <li key={doc}>{doc}</li>)}
            </ul>
          </div>
        )}
        <input ref={inputRef} type="file" multiple accept={ACCEPT} className="sr-only" tabIndex={-1}
          aria-label="Document files" onChange={(e) => handleFiles(e.target.files)} />
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" onClick={() => inputRef.current?.click()}>
            <Upload aria-hidden="true" /> Choose files
          </Button>
          <span className="text-xs">PDF, JPG or PNG, up to 10 MB</span>
        </div>
        {error && <p role="alert" className="text-destructive">{error}</p>}
        {documents.length > 0 && (
          <ul aria-label="Your documents" aria-live="polite" className="divide-y rounded-lg border">
            {documents.map((d) => (
              <li key={d.id} className="flex items-start gap-3 px-3 py-2">
                {d.status === "reading" ? <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin" aria-hidden="true" />
                  : d.status === "failed" ? <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
                  : d.filled ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
                  : <FileText className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-foreground">{d.name}</p>
                  <p className={d.status === "failed" ? "text-destructive" : ""}>{status(d)}</p>
                </div>
                <Button variant="ghost" size="icon-sm" aria-label={`Remove ${d.name} from the list`} onClick={() => onRemove(d.id)}>
                  <X aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
