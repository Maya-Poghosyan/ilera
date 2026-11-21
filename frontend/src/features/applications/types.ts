import type { FieldType } from "@/features/intake/schema";
import type { EligibilityStatus } from "@/features/cases/types";

export type AppStatus = "open" | "in_progress" | "needs_info" | "completed";

export interface ApplicationEntry {
  program: string;
  status: AppStatus;
  form_ids: string[];
  eligibility_status: EligibilityStatus | null;
  confidence: number;
  rationale: string;
  roadblocks: string[];
  required_documents: string[];
  next_steps: string[];
  sources: string[];
  has_forms: boolean;
}

// Shape mirrors the intake `Question` type so it can be handed straight to
// <QuestionField> with no adapter. Extra keys (form_id/fields/interpret) are
// backend metadata the renderer ignores.
export interface AppQuestion {
  field_id: string;
  text: string;
  type: FieldType;
  required: boolean;
  options?: string[];
  why_this_matters?: string;
  helper_text?: string;
  form_id?: string;
  fields?: string[];
  interpret?: boolean;
  // Questions sharing a group_id are one screen; group_prompt heads it.
  group_id?: string;
  group_prompt?: string;
  // Follow-up screens: shown only when an earlier answer satisfies this condition.
  ask_when?: string;
}

export interface StartApplicationResult {
  program: string;
  form_ids: string[];
  autofilled: number;
  total_fields: number;
  questions: AppQuestion[];
  error?: string;
}
