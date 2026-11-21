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
  incident_status: "unreviewed" | "confirmed" | "dismissed";
  created_at: string;
}

export interface JournalCreate {
  case_id: string;
  date: string;
  text: string;
}

export type RenewalUrgency = "overdue" | "due_soon" | "upcoming" | "no_date";

export type RenewalStatus = "active" | "pending" | "overdue";

export interface RenewalItem {
  id: string;
  case_id: string;
  program: string;
  due_date: string | null;
  status: RenewalStatus;
  notes: string;
  last_completed_date: string | null;
  renewal_period_months: number | null;
  created_at: string;
  urgency: RenewalUrgency;
}

export interface RenewalItemCreate {
  case_id: string;
  program: string;
  due_date?: string | null;
  status?: RenewalStatus;
  notes?: string;
  last_completed_date?: string | null;
  renewal_period_months?: number | null;
}

export interface RenewalItemUpdate {
  program?: string;
  due_date?: string | null;
  status?: RenewalStatus;
  notes?: string;
  last_completed_date?: string | null;
  renewal_period_months?: number | null;
}

export interface RecordsSummary {
  timekeeping: TimekeepingEntry[];
  journal: JournalEntry[];
  renewals: RenewalItem[];
  fall_flag: boolean;
}
