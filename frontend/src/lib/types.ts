export type Insurance = "medi-cal" | "medicare" | "private" | "none" | "unknown";

export interface CareRecipient {
  age?: number | null;
  state: string;
  conditions: string[];
  veteran: boolean;
  insurance: Insurance;
  current_benefits: string[];
  care_needs: string[];
}

export interface Caregiver {
  relationship: string;
  employment_status: string;
  hours_per_week?: number | null;
}

export interface Household {
  size?: number | null;
  income_monthly?: number | null;
  assets?: number | null;
}

export interface CaseProfile {
  id: string;
  care_recipient: CareRecipient;
  caregiver: Caregiver;
  household: Household;
  goals: string[];
  followups: Record<string, string>;
  eligibility: Record<string, EligibilityResult>;
}

export type EligibilityStatus = "likely" | "possible" | "unlikely" | "needs_info";

export interface FollowupQuestion {
  program: string;
  id: string;
  prompt: string;
  type: "short_text" | "long_text" | "select" | "multiselect" | "boolean";
  options: string[];
  why: string;
}

export interface EligibilityResult {
  program: string;
  confidence: number;
  status: EligibilityStatus;
  rationale: string;
  roadblocks: string[];
  required_documents: string[];
  next_steps: string[];
  missing_info: string[];
  followups: FollowupQuestion[];
  sources: string[];
}

export interface EligibilityResponse {
  results: EligibilityResult[];
  followups: FollowupQuestion[];
  strategy_notes: string[];
}
