import { request } from "@/lib/http";
import type { CaseProfile, EligibilityResponse } from "@/features/cases/types";

export function determineEligibility(caseId: string): Promise<EligibilityResponse> {
  return request<EligibilityResponse>(`/api/eligibility/${caseId}`, { method: "POST" });
}

export function getEligibility(caseId: string): Promise<EligibilityResponse> {
  return request<EligibilityResponse>(`/api/eligibility/${caseId}`);
}

export function getCase(caseId: string): Promise<CaseProfile> {
  return request<CaseProfile>(`/api/case/${caseId}`);
}
