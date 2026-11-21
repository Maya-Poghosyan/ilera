import { request } from "@/lib/http";
import type { JournalCreate, JournalEntry, RecordsSummary, RenewalItem, RenewalItemCreate, RenewalItemUpdate, TimekeepingCreate, TimekeepingEntry } from "@/features/records/types";

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

export function listRenewals(caseId: string): Promise<RenewalItem[]> {
  return request<RenewalItem[]>(`/api/records/renewals/${caseId}`);
}

export function createRenewal(body: RenewalItemCreate): Promise<RenewalItem> {
  return request<RenewalItem>("/api/records/renewals", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateRenewalItem(id: string, caseId: string, body: RenewalItemUpdate): Promise<RenewalItem> {
  return request<RenewalItem>(`/api/records/renewals/${id}?case_id=${caseId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function deleteRenewalItem(id: string, caseId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/records/renewals/${id}?case_id=${caseId}`, { method: "DELETE" });
}

export function getRecordsSummary(caseId: string): Promise<RecordsSummary> {
  return request<RecordsSummary>(`/api/records/${caseId}`);
}


export function updateTimekeeping(id: string, body: TimekeepingCreate): Promise<TimekeepingEntry> {
  return request(`/api/records/timekeeping/${id}`, { method: "PUT", body: JSON.stringify(body) });
}

export function updateJournal(id: string, body: JournalCreate): Promise<JournalEntry> {
  return request(`/api/records/journal/${id}`, { method: "PUT", body: JSON.stringify(body) });
}

export function reviewIncident(id: string, caseId: string, status: JournalEntry["incident_status"]): Promise<JournalEntry> {
  return request(`/api/records/journal/${id}/incident?case_id=${encodeURIComponent(caseId)}`, {
    method: "PATCH", body: JSON.stringify({ status }),
  });
}
