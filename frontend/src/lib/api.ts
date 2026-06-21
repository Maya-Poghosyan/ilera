import type { Answers, IntakeSchema } from "./intake-schema";
import type { CaseProfile, EligibilityResponse } from "./types";

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

export function getIntakeSchema(): Promise<IntakeSchema> {
  return request<IntakeSchema>("/api/intake/schema");
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

export function getCase(caseId: string): Promise<CaseProfile> {
  return request<CaseProfile>(`/api/case/${caseId}`);
}
