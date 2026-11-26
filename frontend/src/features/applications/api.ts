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

const DOCUMENT_MESSAGES: Record<string, string> = {
  too_large: "This file is too large.",
  unsupported_type: "Use a PDF, JPG or PNG file.",
  encrypted_pdf: "This PDF is password-protected. Save an unlocked copy and try again.",
  too_many_pages: "This PDF has too many pages. Upload just the pages you need.",
  unreadable: "We couldn't open this file.",
  no_text_layer: "This looks like a scanned PDF. Try a clear photo of the page instead.",
  rate_limited: "We're reading a lot of documents right now. Please try again later or enter your answers.",
};

export type DocumentReadResult =
  | { ok: true; answers: Record<string, AnswerValue>; pages: Record<string, number> }
  | { ok: false; message: string };

/** Reads one document and proposes answers to this application's questions. Nothing is saved. */
export async function readApplicationDocument(caseId: string, program: string, file: Blob): Promise<DocumentReadResult> {
  let res: Response;
  try {
    res = await fetch(`/api/applications/${caseId}/${encodeURIComponent(program)}/documents`, {
      method: "POST",
      headers: { "content-type": file.type || "application/octet-stream" },
      body: file,
    });
  } catch {
    return { ok: false, message: "We couldn't reach Ilera. Check your connection and try again." };
  }
  const body = await res.json().catch(() => null) as { answers?: Record<string, AnswerValue>; pages?: Record<string, number>; detail?: unknown } | null;
  if (!res.ok) {
    const code = typeof body?.detail === "string" ? body.detail : "";
    return { ok: false, message: DOCUMENT_MESSAGES[code] ?? "We couldn't read this document. Please enter your answers." };
  }
  return { ok: true, answers: body?.answers ?? {}, pages: body?.pages ?? {} };
}
