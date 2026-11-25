import { request } from "@/lib/http";

// Mailbox connections: OAuth credentials remain server-side.
export type MailboxConnection = {
  id: string;
  case_id: string;
  provider: MailboxProvider;
  status: "pending" | "connected" | "reauthorization_required" | "disconnected";
  mailbox_address: string | null;
  consented_at: string;
  scanning_active: boolean;
};

export type EmailProviders = {
  microsoft: { available: boolean; account_type: "organization" };
  google: { available: boolean };
};

export function getEmailProviders(): Promise<EmailProviders> {
  return request<EmailProviders>("/api/email/providers");
}

export function listMailboxConnections(caseId: string): Promise<MailboxConnection[]> {
  return request<MailboxConnection[]>(`/api/email/connections?case_id=${encodeURIComponent(caseId)}`);
}

export type MailboxProvider = "microsoft" | "google";

export function connectMailbox(provider: MailboxProvider, caseId: string): Promise<{ authorization_url: string }> {
  return request<{ authorization_url: string }>(`/api/email/${provider}/connect`, {
    method: "POST",
    body: JSON.stringify({ case_id: caseId }),
  });
}

export function disconnectMailbox(id: string): Promise<{ disconnected: boolean; subscription_cleanup_pending: boolean }> {
  return request<{ disconnected: boolean; subscription_cleanup_pending: boolean }>(
    `/api/email/connections/${encodeURIComponent(id)}`, { method: "DELETE" },
  );
}
