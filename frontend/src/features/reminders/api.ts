import { request } from "@/lib/http";
import type { Reminder, ReminderCreate, ReminderTemplates, ReminderUpdate } from "@/features/reminders/types";

export function listReminders(caseId?: string): Promise<Reminder[]> {
  return request<Reminder[]>(`/api/reminders${caseId ? `?case_id=${encodeURIComponent(caseId)}` : ""}`);
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

export function getReminderTemplates(): Promise<ReminderTemplates> {
  return request<ReminderTemplates>("/api/reminders/templates");
}
