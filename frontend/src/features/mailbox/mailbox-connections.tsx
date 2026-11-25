"use client";

import { useEffect, useState } from "react";
import { Mail } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/accounts/auth-context";
import { connectMailbox, disconnectMailbox, getEmailProviders, listMailboxConnections, type EmailProviders, type MailboxConnection, type MailboxProvider } from "@/features/mailbox/api";

// Each provider's sign-in page; the browser is only ever sent to this origin.
const PROVIDERS: Record<MailboxProvider, { label: string; origin: string }> = {
  microsoft: { label: "Outlook", origin: "https://login.microsoftonline.com" },
  google: { label: "Gmail", origin: "https://accounts.google.com" },
};

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
    const label = PROVIDERS[url.searchParams.get("provider") === "google" ? "google" : "microsoft"].label;
    // Deferred, and the URL is cleaned in the same callback, so an effect run that is cancelled
    // (React runs effects twice in development) leaves the result for the next run.
    // The callback itself never contains email content.
    const timeout = setTimeout(() => {
      setNotice(result === "connected"
        ? `${label} connected.`
        : `${label} could not connect. Please sign in and try again.`);
      url.searchParams.delete("mailbox");
      url.searchParams.delete("provider");
      window.history.replaceState(null, "", url);
    }, 0);
    return () => clearTimeout(timeout);
  }, []);

  const current = snapshot?.caseId === caseId ? snapshot : null;
  const available = (provider: MailboxProvider) => current?.providers[provider].available ?? false;

  async function connect(provider: MailboxProvider) {
    if (!caseId) return;
    setBusy(true);
    setNotice("");
    try {
      const { authorization_url } = await connectMailbox(provider, caseId);
      const target = new URL(authorization_url);
      if (target.origin !== PROVIDERS[provider].origin) throw new Error("Invalid authorization URL");
      window.location.assign(target.href);
    } catch {
      setNotice(`${PROVIDERS[provider].label} could not connect. Please try again.`);
      setBusy(false);
    }
  }

  async function disconnect(connection: MailboxConnection) {
    const label = PROVIDERS[connection.provider].label;
    setBusy(true);
    try {
      const result = await disconnectMailbox(connection.id);
      setNotice(result.subscription_cleanup_pending
        ? `${label} disconnected and saved credentials deleted. Microsoft notification cleanup is pending.`
        : `${label} disconnected and saved credentials deleted.`);
      setReload((value) => value + 1);
    } catch {
      setNotice(`Could not disconnect ${label}. Please try again.`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-3 rounded-xl border border-brand-subtle bg-card p-4" aria-label="Email connections">
      <div className="flex items-center gap-2 text-primary">
        <Mail className="size-4" />
        <h2 className="text-sm">Email connections</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Connect a mailbox with read-only access. New emails about appointments, deadlines and renewals
        become suggestions you review below. Gmail is checked about once an hour.
      </p>
      {current?.connections.filter((connection) => connection.status !== "disconnected").map((connection) => (
        <div key={connection.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3">
          <span className="text-sm">
            {connection.mailbox_address || PROVIDERS[connection.provider].label} · {connection.scanning_active ? "Connected" : "Sign-in required"}
          </span>
          <div className="flex gap-2">
            {connection.status === "reauthorization_required" && (
              <Button size="sm" disabled={!available(connection.provider) || busy} onClick={() => connect(connection.provider)}>Reconnect</Button>
            )}
            <Button size="sm" variant="outline" disabled={busy} onClick={() => disconnect(connection)}>
              Disconnect
            </Button>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" disabled={!available("microsoft") || !caseId || busy} onClick={() => connect("microsoft")}>
          {busy ? "Please wait…" : "Connect Outlook"}
        </Button>
        <Button variant="outline" disabled={!available("google") || !caseId || busy} onClick={() => connect("google")}>
          {available("google") ? "Connect Gmail" : "Gmail · Coming soon"}
        </Button>
      </div>
      {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
    </section>
  );
}
