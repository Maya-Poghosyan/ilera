import type { ReminderKind, ScheduleFreq } from "@/features/reminders/types";

export const KIND_LABELS: Record<ReminderKind, string> = {
  daily_care_log: "Daily Care Log",
  appointment: "Appointment",
  renewal_deadline: "Renewal Deadline",
  custom: "Custom",
};

export const FREQ_LABELS: Record<ScheduleFreq, string> = { daily: "Daily", weekly: "Weekly", once: "One-time" };

// Index = the API's weekday number (0=Mon … 6=Sun).
export const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
