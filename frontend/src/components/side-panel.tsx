"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

export function SidePanel({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const panel = dialog.current;
    panel?.showModal();
    return () => panel?.close();
  }, []);

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      className="fixed inset-y-0 right-0 left-auto m-0 h-dvh max-h-none w-full max-w-lg overflow-y-auto border-l bg-card p-6 text-foreground shadow-xl backdrop:bg-black/30"
    >
      <div className="mb-6 flex items-start justify-between gap-4">
        <h2 id={titleId} className="text-3xl">{title}</h2>
        <Button type="button" variant="ghost" size="icon" aria-label="Close panel" onClick={onClose}><X /></Button>
      </div>
      {children}
    </dialog>
  );
}
