import type { CaseProfile, EligibilityResponse, Reminder, ReminderCreate, ReminderUpdate, ReminderTemplates } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function submitIntake(profile: Partial<CaseProfile>): Promise<CaseProfile> {
  return request<CaseProfile>("/api/intake", {
    method: "POST",
    body: JSON.stringify({ profile }),
  });
}

export function determineEligibility(caseId: string): Promise<EligibilityResponse> {
  return request<EligibilityResponse>(`/api/eligibility/${caseId}`, { method: "POST" });
}

export function getCase(caseId: string): Promise<CaseProfile> {
  return request<CaseProfile>(`/api/case/${caseId}`);
}

// ---------------------------------------------------------------------------
// Reminders
// ---------------------------------------------------------------------------

export function listReminders(): Promise<Reminder[]> {
  return request<Reminder[]>("/api/reminders");
}

export function createReminder(body: ReminderCreate): Promise<Reminder> {
  return request<Reminder>("/api/reminders", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getReminder(id: string): Promise<Reminder> {
  return request<Reminder>(`/api/reminders/${id}`);
}

export function updateReminder(id: string, body: ReminderUpdate): Promise<Reminder> {
  return request<Reminder>(`/api/reminders/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteReminder(id: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/reminders/${id}`, { method: "DELETE" });
}

export function runReminderNow(id: string): Promise<{ sent: boolean; poke: unknown }> {
  return request<{ sent: boolean; poke: unknown }>(`/api/reminders/${id}/run-now`, { method: "POST" });
}

export function sendTestMessage(message: string): Promise<{ sent: boolean; poke: unknown }> {
  return request<{ sent: boolean; poke: unknown }>("/api/reminders/send", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function getReminderTemplates(): Promise<ReminderTemplates> {
  return request<ReminderTemplates>("/api/reminders/templates");
}

// ---------------------------------------------------------------------------
// Poke scanning
// ---------------------------------------------------------------------------

export function scanForEvents(): Promise<{ scanned: boolean; poke: unknown }> {
  return request<{ scanned: boolean; poke: unknown }>("/api/poke/scan", { method: "POST" });
}
