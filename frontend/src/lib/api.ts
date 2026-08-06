import type { Answers, AnswerValue, IntakeSchema } from "./intake-schema";
import type { AppStatus, ApplicationEntry, CaseProfile, EligibilityResponse, FormSchema, JournalCreate, JournalEntry, RecordsSummary, Reminder, ReminderCreate, ReminderUpdate, ReminderTemplates, RenewalInfo, RenewalUpdate, StartApplicationResult, TimekeepingCreate, TimekeepingEntry } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://api.ileracare.app";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("ilera_token");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "content-type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const res = await fetch(`${BASE}${path}`, {
    headers,
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

export function getIntakeSchema(): Promise<IntakeSchema> {
  return request<IntakeSchema>("/api/intake/schema");
}

export function lookupCounty(zip: string, state: string): Promise<{ county: string }> {
  const query = new URLSearchParams({ zip, state });
  return request<{ county: string }>(`/api/geo/county?${query}`);
}

export function submitIntakeAnswers(answers: Answers): Promise<CaseProfile> {
  return request<CaseProfile>("/api/intake", {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
}

export function determineEligibility(caseId: string): Promise<EligibilityResponse> {
  return request<EligibilityResponse>(`/api/eligibility/${caseId}`, { method: "POST" });
}

export function getEligibility(caseId: string): Promise<EligibilityResponse> {
  return request<EligibilityResponse>(`/api/eligibility/${caseId}`);
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

// Poke scans asynchronously and files results by calling the MCP server, so this
// only confirms the request was queued — poll listSuggestedEvents for results.
export function scanForEvents(
  caseId?: string | null
): Promise<{ requested: boolean; known_event_ids: string[] }> {
  const query = caseId ? `?case_id=${encodeURIComponent(caseId)}` : "";
  return request<{ requested: boolean; known_event_ids: string[] }>(`/api/poke/scan${query}`, {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// Preferences
// ---------------------------------------------------------------------------

export type Preferences = {
  case_id: string;
  monitor_inboxes: boolean;
  monitor_inboxes_updated_at: string;
};

export function getPreferences(caseId: string): Promise<Preferences> {
  return request<Preferences>(`/api/preferences/${caseId}`);
}

export function setMonitorInboxes(caseId: string, on: boolean): Promise<Preferences> {
  return request<Preferences>(`/api/preferences/${caseId}`, {
    method: "PUT",
    body: JSON.stringify({ monitor_inboxes: on }),
  });
}

// ---------------------------------------------------------------------------
// Suggested events (from Poke MCP)
// ---------------------------------------------------------------------------

export type SuggestedEventAPI = {
  id: string;
  /** ISO YYYY-MM-DD. `day` is the day-of-month derived from it. */
  date: string;
  day: number;
  title: string;
  time?: string;
  kind: string;
  description?: string;
  source: string;
};

export function listSuggestedEvents(): Promise<SuggestedEventAPI[]> {
  return request<SuggestedEventAPI[]>("/api/suggested-events");
}

export function deleteSuggestedEvent(id: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/suggested-events/${id}`, { method: "DELETE" });
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

// ---------------------------------------------------------------------------
// Applications
// ---------------------------------------------------------------------------

export function listApplications(caseId: string): Promise<{ applications: ApplicationEntry[] }> {
  return request<{ applications: ApplicationEntry[] }>(`/api/applications/${caseId}`);
}

export function updateAppStatus(
  caseId: string,
  program: string,
  status: AppStatus
): Promise<{ program: string; status: string }> {
  return request(`/api/applications/${caseId}/${encodeURIComponent(program)}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function startApplication(
  caseId: string,
  program: string
): Promise<StartApplicationResult> {
  return request<StartApplicationResult>(
    `/api/applications/${caseId}/${encodeURIComponent(program)}/start`,
    { method: "POST" }
  );
}

export async function submitApplicationAnswers(
  caseId: string,
  program: string,
  answers: Record<string, AnswerValue>
): Promise<Blob> {
  const res = await fetch(
    `${BASE}/api/applications/${caseId}/${encodeURIComponent(program)}/submit`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ answers }),
    }
  );
  if (!res.ok) throw new Error(`Submit failed: ${res.status}`);
  return res.blob();
}

export async function previewApplication(
  caseId: string,
  program: string,
  answers: Record<string, AnswerValue>
): Promise<Blob> {
  const res = await fetch(
    `${BASE}/api/applications/${caseId}/${encodeURIComponent(program)}/preview`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ answers }),
    }
  );
  if (!res.ok) throw new Error(`Preview failed: ${res.status}`);
  return res.blob();
}

export function completeApplication(
  caseId: string,
  program: string
): Promise<{ program: string; status: string }> {
  return request(`/api/applications/${caseId}/${encodeURIComponent(program)}/complete`, {
    method: "POST",
  });
}
