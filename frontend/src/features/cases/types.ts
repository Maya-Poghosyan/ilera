export type Insurance = "medi-cal" | "medicare" | "private" | "none" | "unknown";

export interface CareRecipient {
  name: string;
  date_of_birth: string;
  age?: number | null;
  gender: string;
  state: string;
  street_address: string;
  city: string;
  county: string;
  zip_code: string;
  phone: string;
  email: string;
  ssn: string;
  conditions: string[];
  veteran: boolean;
  insurance: Insurance;
  current_benefits: string[];
  care_needs: string[];
}

export interface Caregiver {
  name: string;
  relationship: string;
  employment_status: string;
  hours_per_week?: number | null;
  phone: string;
  email: string;
  address: string;
}

export interface Household {
  size?: number | null;
  income_monthly?: number | null;
}

export type BandStatus = "idle" | "processing" | "complete" | "error";

export interface SpecialistFinding {
  program: string;
  doc_key: string;
  match_level: MatchLevel;
  notes: string[];
  cross_programs: string[];
  citations: string[];
  complete: boolean;
  updated_at: string;
}

export interface CaseProfile {
  id: string;
  care_recipient: CareRecipient;
  caregiver: Caregiver;
  household: Household;
  answers: Record<string, unknown>;
  followups: Record<string, string>;
  eligibility: Record<string, EligibilityResult>;
  band_chat_id: string;
  band_status: BandStatus;
  band_error: string;
  findings: Record<string, SpecialistFinding>;
  expected_specialists: string[];
  strategy: string;
  strategy_complete: boolean;
}

export type EligibilityStatus = "likely" | "possible" | "unlikely" | "needs_info";

export type MatchLevel = "none" | "low" | "medium" | "likely" | "very_likely";

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
  match_level: MatchLevel;
  rationale: string;
  roadblocks: string[];
  required_documents: string[];
  next_steps: string[];
  missing_info: string[];
  followups: FollowupQuestion[];
  sources: string[];
}

export interface EligibilityResponse {
  status: BandStatus;
  results: EligibilityResult[];
  strategy: string;
  strategy_complete: boolean;
  expected: string[];
  completed: string[];
  error: string;
}
