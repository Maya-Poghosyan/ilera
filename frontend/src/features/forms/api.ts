import { request } from "@/lib/http";
import type { FormSchema } from "@/features/forms/types";

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
  return `/api/forms/${formId}/${caseId}/download`;
}
