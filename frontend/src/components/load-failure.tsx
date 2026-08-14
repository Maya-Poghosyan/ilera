"use client";

import { Button } from "@/components/ui/button";

/** Shown when a page can't load its data.
 *
 * The API is already retried a couple of times underneath, so reaching here means the outage
 * outlasted that — the caregiver needs a way to try again without knowing to reload, and no
 * mention of servers or ports, which tells them nothing they can act on. */
export function LoadFailure({
  message,
  onRetry,
  retrying,
}: {
  message: string;
  onRetry: () => void;
  retrying?: boolean;
}) {
  return (
    <main className="mx-auto flex max-w-xl flex-1 flex-col items-center justify-center gap-4 px-6 py-20 text-center">
      <p className="text-muted-foreground">{message}</p>
      <Button variant="outline" onClick={onRetry} disabled={retrying}>
        {retrying ? "Trying again…" : "Try again"}
      </Button>
    </main>
  );
}
