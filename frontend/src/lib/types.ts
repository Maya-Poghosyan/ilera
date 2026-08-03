import type { FieldType } from "@/lib/intake-schema";

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
  /** IANA zone `time` is interpreted in; backend default when omitted. */
  timezone?: string | null;
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
// Records & Renewal
// ---------------------------------------------------------------------------

export type ServiceType = "personal_care" | "domestic" | "paramedical" | "accompaniment";

export interface TimekeepingEntry {
  id: string;
  case_id: string;
  date: string;
  hours: number;
  start_time: string | null;
  end_time: string | null;
  service_type: ServiceType;
  tasks: string[];
  notes: string;
  created_at: string;
}

export interface TimekeepingCreate {
  case_id: string;
  date: string;
  hours: number;
  start_time?: string;
  end_time?: string;
  service_type?: ServiceType;
  tasks: string[];
  notes?: string;
}

export interface JournalEntry {
  id: string;
  case_id: string;
  date: string;
  text: string;
  fall_flagged: boolean;
  created_at: string;
}

export interface JournalCreate {
  case_id: string;
  date: string;
  text: string;
}

export interface RenewalInfo {
  case_id: string;
  program: string;
  due_date: string | null;
  status: string;
}

export interface RenewalUpdate {
  program?: string;
  due_date?: string;
  status?: string;
}

export interface RecordsSummary {
  timekeeping: TimekeepingEntry[];
  journal: JournalEntry[];
  renewal: RenewalInfo;
  fall_flag: boolean;
}

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

// ---------------------------------------------------------------------------
// Applications
// ---------------------------------------------------------------------------

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
