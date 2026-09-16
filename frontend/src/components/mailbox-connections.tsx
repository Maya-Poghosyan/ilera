"use client";

import { useEffect, useState } from "react";
import { Mail } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import {
  connectMicrosoftMailbox,
  disconnectMailbox,
  getEmailProviders,
  listMailboxConnections,
  type EmailProviders,
  type MailboxConnection,
} from "@/lib/api";

export function MailboxConnections() {
  const { user } = useAuth();
  const caseId = user?.case_id;
  const [snapshot, setSnapshot] = useState<{
    caseId: string;
    providers: EmailProviders;
    connections: MailboxConnection[];
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!caseId) return;
    let cancelled = false;
    Promise.all([getEmailProviders(), listMailboxConnections(caseId)])
      .then(([providers, connections]) => {
        if (!cancelled) setSnapshot({ caseId, providers, connections });
      })
      .catch(() => {
        if (!cancelled) setNotice("Mailbox connection status is unavailable. Please try again.");
      });
    return () => { cancelled = true; };
  }, [caseId, reload]);

  useEffect(() => {
    const url = new URL(window.location.href);
    const result = url.searchParams.get("mailbox");
    if (!result) return;
    // Defer the notification; the callback itself never contains email content.
    const timeout = setTimeout(() => {
      setNotice(result === "connected"
        ? "Outlook connected. Automatic email scanning is not available yet."
        : "Outlook could not connect. Please sign in and try again.");
    }, 0);
    url.searchParams.delete("mailbox");
    window.history.replaceState(null, "", url);
    return () => clearTimeout(timeout);
  }, []);

  const current = snapshot?.caseId === caseId ? snapshot : null;
  const available = current?.providers.microsoft.available ?? false;

  async function connect() {
    if (!caseId) return;
    setBusy(true);
    setNotice("");
    try {
      const { authorization_url } = await connectMicrosoftMailbox(caseId);
      const target = new URL(authorization_url);
      if (target.origin !== "https://login.microsoftonline.com") throw new Error("Invalid authorization URL");
      window.location.assign(target.href);
    } catch {
      setNotice("Outlook could not connect. Please try again.");
      setBusy(false);
    }
  }

  async function disconnect(id: string) {
    setBusy(true);
    try {
      const result = await disconnectMailbox(id);
      setNotice(result.subscription_cleanup_pending
        ? "Outlook disconnected and saved credentials deleted. Microsoft notification cleanup is pending."
        : "Outlook disconnected and saved credentials deleted.");
      setReload((value) => value + 1);
    } catch {
      setNotice("Could not disconnect Outlook. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded-xl border border-brand-subtle bg-card p-4" aria-label="Email connections">
      <div className="flex items-center gap-2 text-primary">
        <Mail className="size-4" />
        <h2 className="text-sm font-semibold">Email connections</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        {available
          ? "Connect your Microsoft 365 work or school mailbox with read-only access. Automatic email scanning is coming soon."
          : "Microsoft 365 connections are being set up. Email scanning and Gmail connections are coming soon."}
      </p>
      {current?.connections.filter((connection) => connection.status !== "disconnected").map((connection) => (
        <div key={connection.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
          <span className="text-sm">
            {connection.mailbox_address || "Outlook"} · {connection.status === "connected" ? "Connected; scanning not active" : "Sign-in required"}
          </span>
          <div className="flex gap-2">
            {connection.status === "reauthorization_required" && (
              <Button size="sm" disabled={!available || busy} onClick={connect}>Reconnect</Button>
            )}
            <Button size="sm" variant="outline" disabled={busy} onClick={() => disconnect(connection.id)}>
              Disconnect
            </Button>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" disabled={!available || !caseId || busy} onClick={connect}>
          {busy ? "Please wait…" : "Connect Outlook"}
        </Button>
        <Button variant="outline" disabled>Gmail · Coming soon</Button>
      </div>
      {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
    </section>
  );
}
