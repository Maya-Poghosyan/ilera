"use client";
// The intake's shared document collection. Kept in memory only, never in the saved draft.
import { useCallback, useState } from "react";
import { readDocument, type Suggestion } from "@/features/intake/documents/reading";
import { questionFor } from "@/features/intake/documents/suggestions";

export type IntakeDocument = { id: string; name: string } & (
  | { status: "reading" }
  | { status: "read"; suggestions: Suggestion[] }
  | { status: "failed"; message: string }
);
export interface PendingSuggestion { key: string; documentName: string; suggestion: Suggestion }

export function useIntakeDocuments() {
  const [documents, setDocuments] = useState<IntakeDocument[]>([]);
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());

  const add = useCallback((files: File[]) => {
    for (const file of files) {
      const id = crypto.randomUUID();
      setDocuments(prev => [...prev, { id, name: file.name, status: "reading" }]);
      void readDocument(file).then(result => setDocuments(prev => prev.map(d => d.id !== id ? d
        : result.ok ? { id, name: d.name, status: "read", suggestions: result.suggestions }
        : { id, name: d.name, status: "failed", message: result.message })));
    }
  }, []);

  const pendingFor = useCallback((questionId: string): PendingSuggestion[] => documents.flatMap(d =>
    d.status !== "read" ? [] : d.suggestions.flatMap((suggestion, i) => {
      const key = `${d.id}:${i}`;
      return questionFor(suggestion) === questionId && !dismissed.has(key) ? [{ key, documentName: d.name, suggestion }] : [];
    })), [documents, dismissed]);

  return {
    documents,
    add,
    remove: (id: string) => setDocuments(prev => prev.filter(d => d.id !== id)),
    dismiss: (key: string) => setDismissed(prev => new Set(prev).add(key)),
    reset: () => { setDocuments([]); setDismissed(new Set()); },
    pendingFor,
  };
}
