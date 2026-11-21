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
