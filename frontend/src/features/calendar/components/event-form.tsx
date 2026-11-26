"use client";

import { useRef, useState, type FormEvent } from "react";
import { SidePanel } from "@/components/side-panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createCalendarEvent } from "@/features/calendar/api";
import type { EventKind } from "@/features/calendar/use-calendar";

export function EventForm({ kind, onClose, onSaved }: { kind: EventKind; onClose: () => void; onSaved: () => void }) {
  const requestId = useRef<string | null>(null);
  const saving = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving.current) return;
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") ?? "").trim();
    if (!title) {
      setError("Enter a title.");
      return;
    }
    saving.current = true;
    setBusy(true);
    setError("");
    try {
      requestId.current ??= crypto.randomUUID();
      await createCalendarEvent({
        request_id: requestId.current,
        title,
        date: String(form.get("date")),
        time: String(form.get("time") ?? "") || null,
        kind,
      });
      onSaved();
    } catch {
      setError("Could not save the event. Please try again.");
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  return (
    <SidePanel title={`Add ${kind.toLowerCase()}`} onClose={() => { if (!saving.current) onClose(); }}>
      <form className="space-y-4" onSubmit={submit}>
        <label className="block space-y-1"><span>Title</span><Input name="title" maxLength={120} required /></label>
        <label className="block space-y-1"><span>Date</span><Input name="date" type="date" required /></label>
        <label className="block space-y-1"><span>Time (optional)</span><Input name="time" type="time" /></label>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <div className="flex gap-2">
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save event"}</Button>
          <Button type="button" variant="outline" disabled={busy} onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </SidePanel>
  );
}
