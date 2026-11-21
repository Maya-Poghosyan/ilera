import { request } from "@/lib/http";

export type SuggestedEventAPI = {
  id: string;
  /** ISO YYYY-MM-DD, or null when email did not establish a date. */
  date: string | null;
  date_status: "known" | "ambiguous" | "missing";
  timezone?: string | null;
  day: number;
  title: string;
  time?: string;
  kind: string;
  description?: string;
  source: string;
  confidence?: number | null;
  action_required?: string | null;
  status: "pending" | "accepted" | "dismissed";
};

/** A committed calendar entry (an accepted suggestion or a manual event). */
export type CalendarEventAPI = {
  id: string;
  date: string | null;
  timezone?: string | null;
  day: number;
  title: string;
  time?: string;
  kind: string;
  description?: string;
  source: string;
  source_suggestion_id?: string | null;
};

export function listSuggestedEvents(): Promise<SuggestedEventAPI[]> {
  return request<SuggestedEventAPI[]>("/api/suggested-events");
}

export function reviewSuggestedEvent(
  id: string,
  status: "pending" | "accepted" | "dismissed"
): Promise<SuggestedEventAPI> {
  return request<SuggestedEventAPI>(`/api/suggested-events/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function deleteSuggestedEvent(id: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/suggested-events/${id}`, { method: "DELETE" });
}

export function listCalendarEvents(): Promise<CalendarEventAPI[]> {
  return request<CalendarEventAPI[]>("/api/calendar-events");
}

export function deleteCalendarEvent(id: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/api/calendar-events/${id}`, { method: "DELETE" });
}
