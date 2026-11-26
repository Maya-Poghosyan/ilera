"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/accounts/auth-context";
import { connectMailbox, disconnectMailbox, getEmailProviders, listMailboxConnections, type EmailProviders, type MailboxConnection, type MailboxProvider } from "@/features/mailbox/api";

// Each provider's sign-in page; the browser is only ever sent to this origin.
const PROVIDERS: Record<MailboxProvider, { label: string; origin: string }> = {
  microsoft: { label: "Outlook", origin: "https://login.microsoftonline.com" },
  google: { label: "Gmail", origin: "https://accounts.google.com" },
};

function ProviderLogo({ provider }: { provider: MailboxProvider }) {
  return provider === "google" ? (
    <svg className="size-9 transition-transform group-hover:scale-110 group-focus-visible:scale-110" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#4285f4" d="M4 36V14l8 6v18H6a2 2 0 0 1-2-2Z" />
      <path fill="#34a853" d="M36 20l8-6v22a2 2 0 0 1-2 2h-6Z" />
      <path fill="#ea4335" d="M12 10l12 9 12-9v10l-12 9-12-9Z" />
      <path fill="#c5221f" d="M4 14v-2a4 4 0 0 1 6-3l2 1v10Z" />
      <path fill="#fbbc04" d="M36 10l2-1a4 4 0 0 1 6 3v2l-8 6Z" />
    </svg>
  ) : (
    <svg className="size-9 transition-transform group-hover:scale-110 group-focus-visible:scale-110" viewBox="0 0 48 48" aria-hidden="true">
      <rect x="17" y="7" width="24" height="32" rx="3" fill="#0078d4" />
      <path fill="#50d9ff" d="M20 13h8v8h-8zM30 13h8v8h-8z" />
      <path fill="#1490df" d="M16 25h28v15a2 2 0 0 1-2 2H18a2 2 0 0 1-2-2Z" />
      <path fill="#28a8ea" d="m16 25 14 9 14-9v15a2 2 0 0 1-2 2H18a2 2 0 0 1-2-2Z" />
      <rect x="4" y="13" width="21" height="23" rx="2" fill="#0364b8" />
      <ellipse cx="14.5" cy="24.5" rx="4.5" ry="6" fill="none" stroke="white" strokeWidth="2.5" />
    </svg>
  );
}

export function MailboxConnections({ description, className = "rounded-xl border border-brand-subtle bg-card p-5" }: {
  description?: string;
  className?: string;
}) {
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
    const refresh = () => setReload((value) => value + 1);
    const refreshOnCallback = (event: StorageEvent) => {
      if (event.key === "ilera-mailbox-updated") refresh();
    };
    window.addEventListener("focus", refresh);
    window.addEventListener("storage", refreshOnCallback);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("storage", refreshOnCallback);
    };
  }, []);

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
      try { localStorage.setItem("ilera-mailbox-updated", String(Date.now())); } catch { /* Focus also refreshes the original tab. */ }
    }, 0);
    return () => clearTimeout(timeout);
  }, []);

  const current = snapshot?.caseId === caseId ? snapshot : null;
  const available = (provider: MailboxProvider) => current?.providers[provider].available ?? false;

  async function connect(provider: MailboxProvider) {
    if (!caseId) return;
    const signIn = window.open("about:blank", "_blank");
    if (!signIn) {
      setNotice("Allow pop-ups to open the email sign-in tab.");
      return;
    }
    signIn.opener = null;
    setBusy(true);
    setNotice("");
    try {
      const { authorization_url } = await connectMailbox(provider, caseId);
      const target = new URL(authorization_url);
      if (target.origin !== PROVIDERS[provider].origin) throw new Error("Invalid authorization URL");
      signIn.location.replace(target.href);
    } catch {
      signIn.close();
      setNotice(`${PROVIDERS[provider].label} could not connect. Please try again.`);
    } finally {
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
    <section className={`space-y-4 ${className}`} aria-labelledby="email-connections-title">
      <div className="space-y-1">
        <h2 id="email-connections-title" className="text-2xl">Connect email inbox <span className="text-lg text-muted-foreground">(optional)</span></h2>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      <div className="grid gap-2">
        {(["google", "microsoft"] as const).map((provider) => {
          const { label } = PROVIDERS[provider];
          const connections = current?.connections.filter((item) => item.provider === provider
            && (item.status === "connected" || item.status === "reauthorization_required")) ?? [];
          const connected = connections.filter((item) => item.status === "connected");
          const contents = <>
            <ProviderLogo provider={provider} />
            <span className="min-w-0 break-words text-left">
              {connected.length ? connected.map((item) => (
                <span key={item.id} className="block">
                  {item.mailbox_address ? `Connected to ${item.mailbox_address}` : "Connected"}
                </span>
              )) : "Not connected"}
            </span>
          </>;
          const tile = "group flex w-full cursor-pointer items-center gap-3 rounded-lg border px-4 py-2 text-sm [&>svg]:shrink-0";
          return connections.length ? (
            <details key={provider}>
              <summary className={`${tile} list-none`} aria-label={`Manage ${label}`}>{contents}</summary>
              <div className="space-y-2 p-2">
                {connections.map((item) => <div key={item.id} className="flex flex-wrap gap-2">
                  {item.status === "reauthorization_required" && <Button size="sm" variant="outline" disabled={!available(provider) || busy} onClick={() => connect(provider)} aria-label={`Reconnect ${label}`}>Reconnect</Button>}
                  <Button size="sm" variant="outline" disabled={busy} aria-label={`Disconnect ${item.mailbox_address || label}`} onClick={() => disconnect(item)}>Disconnect</Button>
                </div>)}
              </div>
            </details>
          ) : (
            <button key={provider} type="button" className={`${tile} disabled:cursor-default disabled:opacity-60`} disabled={!available(provider) || !caseId || busy} aria-label={`Connect ${label}`} onClick={() => void connect(provider)}>
              {contents}
            </button>
          );
        })}
      </div>
      {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
    </section>
  );
}
