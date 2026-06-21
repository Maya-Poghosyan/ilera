import type { CaseProfile, EligibilityResponse, FormSchema, JournalCreate, JournalEntry, RecordsSummary, Reminder, ReminderCreate, ReminderUpdate, ReminderTemplates, RenewalInfo, RenewalUpdate, TimekeepingCreate, TimekeepingEntry } from "./types";

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

// ---------------------------------------------------------------------------
// Records & Renewal
// ---------------------------------------------------------------------------

export function listTimekeeping(caseId: string): Promise<TimekeepingEntry[]> {
  return request<TimekeepingEntry[]>(`/api/records/timekeeping/${caseId}`);
}

export function createTimekeeping(body: TimekeepingCreate): Promise<TimekeepingEntry> {
  return request<TimekeepingEntry>("/api/records/timekeeping", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteTimekeepingEntry(id: string, caseId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/records/timekeeping/${id}?case_id=${caseId}`, { method: "DELETE" });
}

export function listJournal(caseId: string): Promise<JournalEntry[]> {
  return request<JournalEntry[]>(`/api/records/journal/${caseId}`);
}

export function createJournal(body: JournalCreate): Promise<JournalEntry> {
  return request<JournalEntry>("/api/records/journal", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteJournalEntry(id: string, caseId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/records/journal/${id}?case_id=${caseId}`, { method: "DELETE" });
}

export function getRenewal(caseId: string): Promise<RenewalInfo> {
  return request<RenewalInfo>(`/api/records/renewal/${caseId}`);
}

export function updateRenewal(caseId: string, body: RenewalUpdate): Promise<RenewalInfo> {
  return request<RenewalInfo>(`/api/records/renewal/${caseId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function getRecordsSummary(caseId: string): Promise<RecordsSummary> {
  return request<RecordsSummary>(`/api/records/${caseId}`);
}

// ---------------------------------------------------------------------------
// Forms
// ---------------------------------------------------------------------------

export function listForms(): Promise<{ forms: FormSchema[] }> {
  return request<{ forms: FormSchema[] }>("/api/forms");
}

export function getFormFields(formId: string, caseId: string) {
  return request<{
    resolved: Record<string, unknown>;
    missing: string[];
    needs_user_input: Array<{ field: string; label: string; type: string }>;
  }>(`/api/forms/${formId}/${caseId}`);
}

export function getFormDownloadUrl(formId: string, caseId: string): string {
  return `${BASE}/api/forms/${formId}/${caseId}/download`;
}
