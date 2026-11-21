import { request } from "@/lib/http";

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
