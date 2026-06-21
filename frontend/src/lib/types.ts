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

// ---------------------------------------------------------------------------
// Reminders
// ---------------------------------------------------------------------------

export type ReminderKind = "daily_care_log" | "appointment" | "renewal_deadline" | "custom";
export type ScheduleFreq = "daily" | "weekly" | "once";

export interface ReminderSchedule {
  freq: ScheduleFreq;
  time: string;
  weekday?: number | null;
  date?: string | null;
}

export interface Reminder {
  id: string;
  case_id?: string | null;
  kind: ReminderKind;
  message: string;
  schedule: ReminderSchedule;
  next_run?: string | null;
  active: boolean;
  created_at: string;
  last_sent_at?: string | null;
}

export interface ReminderCreate {
  case_id?: string | null;
  kind?: ReminderKind;
  message?: string;
  schedule?: Partial<ReminderSchedule>;
  active?: boolean;
}

export interface ReminderUpdate {
  message?: string;
  schedule?: ReminderSchedule;
  active?: boolean;
  kind?: ReminderKind;
}

export type ReminderTemplates = Record<string, {
  kind: ReminderKind;
  message: string;
  schedule: Partial<ReminderSchedule>;
}>;

// ---------------------------------------------------------------------------
// Forms
// ---------------------------------------------------------------------------

export interface FormSchema {
  form_id: string;
  title: string;
  program: string;
  agency: string;
  source_url: string;
  pdf_path: string;
  total_pdf_fields: number;
  mapped_fields: number;
  total_schema_fields: number;
}
