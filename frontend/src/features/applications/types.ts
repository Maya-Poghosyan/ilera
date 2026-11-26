import type { FieldType } from "@/features/intake/schema";
import type { EligibilityStatus } from "@/features/cases/types";

export type AppStatus = "open" | "in_progress" | "needs_info" | "completed" | "pending_determination" | "accepted" | "denied" | "archived";

export const APP_STATUS_LABELS: Record<AppStatus, string> = {
  open: "Open",
  in_progress: "In progress",
  needs_info: "Needs information",
  completed: "Completed",
  pending_determination: "Pending determination",
  accepted: "Approved",
  denied: "Denied",
  archived: "Archived",
};

export type ApplicationStage = "update_information" | "gather_documents" | "review_forms" | "follow_up";

export const STAGE_LABELS: Record<ApplicationStage, string> = {
  update_information: "Update Information",
  gather_documents: "Gather documents",
  review_forms: "Review application forms",
  follow_up: "Follow-up Steps",
};

export interface ApprovalDetails {
  approval_date?: string;
  effective_date?: string;
  due_date?: string;
  benefit_end_date?: string;
  tax_year?: number;
}

export interface ApplicationEntry {
  program: string;
  status: AppStatus;
  determination?: "approved" | "denied" | null;
  renewal_record_id?: string | null;
  form_ids: string[];
  stage: ApplicationStage;
  ready_documents: string[];
  completed_follow_ups: string[];
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
