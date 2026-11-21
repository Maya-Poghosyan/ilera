import type { JournalEntry, RenewalStatus, RenewalUrgency, ServiceType } from "@/features/records/types";

export const SERVICE_LABELS: Record<ServiceType, string> = {
  personal_care: "Personal Care",
  domestic: "Domestic",
  paramedical: "Paramedical",
  accompaniment: "Accompaniment",
};

export const URGENCY_BADGE: Record<RenewalUrgency, { label: string; className: string }> = {
  overdue: { label: "Overdue", className: "bg-red-100 text-red-800 border border-red-300" },
  due_soon: { label: "Due soon", className: "bg-amber-100 text-amber-800 border border-amber-300" },
  upcoming: { label: "Upcoming", className: "bg-emerald-100 text-emerald-800 border border-emerald-300" },
  no_date: { label: "No date set", className: "bg-muted text-muted-foreground border" },
};

// Overdue first, then soonest-due, then upcoming, then undated.
export const URGENCY_ORDER: Record<RenewalUrgency, number> = { overdue: 0, due_soon: 1, upcoming: 2, no_date: 3 };

export const RENEWAL_STATUSES: RenewalStatus[] = ["active", "pending", "overdue"];
export const STATUS_LABELS: Record<RenewalStatus, string> = { active: "Active", pending: "Pending", overdue: "Overdue" };

// How a flagged possible-fall entry reads to the caregiver, by review state.
export const INCIDENT_BADGE: Record<JournalEntry["incident_status"], { label: string; className: string }> = {
  unreviewed: { label: "Possible fall — needs review", className: "bg-amber-100 text-amber-800 border border-amber-300" },
  confirmed: { label: "Confirmed fall", className: "bg-red-100 text-red-800 border border-red-300" },
  dismissed: { label: "Not a fall", className: "bg-muted text-muted-foreground border" },
};

const MS_PER_DAY = 1000 * 60 * 60 * 24;

/** Human, at-a-glance phrasing of a due date, e.g. "Due in 12 days" or "5 days overdue". */
export function relativeDue(iso: string | null): string {
  if (!iso) return "No due date set";
  const days = Math.round((new Date(iso + "T00:00:00").setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / MS_PER_DAY);
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  if (days === -1) return "1 day overdue";
  if (days < 0) return `${Math.abs(days)} days overdue`;
  return `Due in ${days} days`;
}

export function formatDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
