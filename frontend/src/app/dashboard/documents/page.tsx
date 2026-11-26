"use client";

import { useEffect, useRef, useState } from "react";
import { FileText, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/accounts/auth-context";
import { pdfThumbnail } from "@/features/documents/pdf-thumbnail";
import { deleteDocument, listDocuments, saveDocument, type SavedDocument } from "@/features/documents/storage";

const ACCEPTED = ["application/pdf", "image/jpeg", "image/png"];
const MAX_BYTES = 10 * 1024 * 1024;

function DocumentTile({ entry, onRemove }: { entry: SavedDocument; onRemove: () => void }) {
  const [urls, setUrls] = useState<{ download: string; thumbnail: string | null } | null>(null);
  useEffect(() => {
    const download = URL.createObjectURL(entry.file);
    const thumbnail = entry.thumbnail ? URL.createObjectURL(entry.thumbnail)
      : entry.file.type.startsWith("image/") ? download : null;
    const next = { download, thumbnail };
    // Assign only after mount so object URLs always have a matching cleanup.
    const timer = window.setTimeout(() => setUrls(next), 0);
    return () => {
      window.clearTimeout(timer);
      URL.revokeObjectURL(download);
      if (thumbnail && thumbnail !== download) URL.revokeObjectURL(thumbnail);
    };
  }, [entry]);

  return (
    <li className="relative min-w-0">
      <a download={entry.file.name} href={urls?.download} aria-label={`Download ${entry.file.name}`}
        className="group block rounded-lg focus-visible:outline-2 focus-visible:outline-primary">
        <div className="flex aspect-[4/5] items-center justify-center overflow-hidden rounded-lg border bg-muted/40 group-hover:bg-muted">
          {urls?.thumbnail ? (
            // Blob URLs resolve in the browser and require no image proxy.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={urls.thumbnail} alt="" className="size-full object-contain p-2" />
          ) : <FileText aria-hidden="true" className="size-10 text-muted-foreground" />}
        </div>
        <p className="mt-2 break-words text-sm font-medium">{entry.file.name}</p>
      </a>
      <Button type="button" size="icon-sm" variant="outline" className="absolute right-2 top-2 bg-card"
        aria-label={`Remove ${entry.file.name}`} onClick={onRemove}><Trash2 /></Button>
    </li>
  );
}

function DocumentGallery({ owner }: { owner: string }) {
  const input = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<SavedDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    listDocuments(owner)
      .then((files) => { if (active) setDocuments(files); })
      .catch(() => { if (active) setError("Could not load documents saved in this browser."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [owner]);

  async function upload(files: File[]) {
    if (!files.length) return;
    setBusy(true);
    setError("");
    const errors: string[] = [];
    try {
      for (const file of files) {
        if (!ACCEPTED.includes(file.type) || !file.size || file.size > MAX_BYTES) {
          errors.push(`${file.name}: choose a PDF, JPG or PNG up to 10 MB.`);
          continue;
        }
        const thumbnail = file.type === "application/pdf" ? await pdfThumbnail(file).catch(() => null) : null;
        const entry = { owner, id: crypto.randomUUID(), file, thumbnail, createdAt: Date.now() };
        try {
          await saveDocument(entry);
          setDocuments((current) => [entry, ...current]);
        } catch {
          errors.push(`Could not save ${file.name} in this browser.`);
        }
      }
    } finally {
      setError(errors.join(" "));
      setBusy(false);
    }
  }

  async function remove(entry: SavedDocument) {
    if (!window.confirm(`Remove ${entry.file.name} from Documents?`)) return;
    setError("");
    try {
      await deleteDocument(owner, entry.id);
      setDocuments((current) => current.filter(({ id }) => id !== entry.id));
    } catch {
      setError(`Could not remove ${entry.file.name}.`);
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="page-title">Documents</h1>
          <p className="text-sm text-muted-foreground">PDF, JPG or PNG, up to 10 MB each.</p>
        </div>
        <input ref={input} type="file" multiple accept={ACCEPTED.join(",")} aria-label="Upload files" className="sr-only" tabIndex={-1}
          onChange={(event) => { const files = Array.from(event.target.files ?? []); event.target.value = ""; void upload(files); }} />
        <Button disabled={busy || loading} onClick={() => input.current?.click()}>
          <Upload /> {busy ? "Saving files…" : "Upload documents"}
        </Button>
      </header>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {loading ? <p role="status">Loading documents…</p> : documents.length ? (
        <ul aria-label="Uploaded documents" className="grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-5">
          {documents.map((entry) => <DocumentTile key={entry.id} entry={entry} onRemove={() => void remove(entry)} />)}
        </ul>
      ) : <p className="text-muted-foreground">No documents uploaded yet.</p>}
    </div>
  );
}

export default function DocumentsPage() {
  const { user } = useAuth();
  return user ? <DocumentGallery key={user.id} owner={user.id} /> : null;
}
