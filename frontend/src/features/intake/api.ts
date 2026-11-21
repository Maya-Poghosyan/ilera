import { request } from "@/lib/http";
import type { Answers, IntakeSchema } from "@/features/intake/schema";
import type { CaseProfile } from "@/features/cases/types";

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
