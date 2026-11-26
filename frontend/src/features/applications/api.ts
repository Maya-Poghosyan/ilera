import { request } from "@/lib/http";
import type { AnswerValue } from "@/features/intake/schema";
import type { AppStatus, ApplicationEntry, ApplicationStage, ApprovalDetails, StartApplicationResult } from "@/features/applications/types";

export function listApplications(caseId: string): Promise<{ applications: ApplicationEntry[] }> {
  return request<{ applications: ApplicationEntry[] }>(`/api/applications/${caseId}`);
}

export function updateAppStatus(
  caseId: string,
  program: string,
  status: AppStatus | "restore",
  approval?: ApprovalDetails,
): Promise<{ program: string; status: AppStatus; renewal_record_id?: string | null }> {
  return request(`/api/applications/${caseId}/${encodeURIComponent(program)}`, {
    method: "PATCH",
    body: JSON.stringify({ status, approval }),
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
    `/api/applications/${caseId}/${encodeURIComponent(program)}/submit`,
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
    `/api/applications/${caseId}/${encodeURIComponent(program)}/preview`,
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
): Promise<{ program: string; status: AppStatus }> {
  return request(`/api/applications/${caseId}/${encodeURIComponent(program)}/complete`, {
    method: "POST",
  });
}

export function saveApplicationProgress(caseId: string, program: string, progress: {
  stage: ApplicationStage;
  answers?: Record<string, AnswerValue>;
  ready_documents?: string[];
  completed_follow_ups?: string[];
}): Promise<{ stage: ApplicationStage; status: AppStatus }> {
  return request(`/api/applications/${caseId}/${encodeURIComponent(program)}/progress`, {
    method: "PUT",
    body: JSON.stringify(progress),
  });
}
