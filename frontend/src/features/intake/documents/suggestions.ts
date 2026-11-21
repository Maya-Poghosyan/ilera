// How a reviewed suggestion becomes an intake answer.
import type { Answers, AnswerValue, HouseholdMember } from "@/features/intake/schema";
import type { HouseholdPerson, Suggestion } from "@/features/intake/documents/reading";

export const ROSTER_QUESTION = "household.members";

/** The question a suggestion is reviewed on. */
export function questionFor(s: Suggestion): string {
  return s.kind === "member_income" ? ROSTER_QUESTION : s.field_id;
}

function rosterIndex(members: HouseholdMember[], person: HouseholdPerson, answers: Answers): number {
  // A caregiver who is the recipient's spouse is the roster's spouse entry.
  const kind = person === "caregiver" && answers["caregiver.relationship"] === "Spouse or domestic partner" ? "spouse" : person;
  return kind === "other_household_member" ? -1 : members.findIndex(m => m.kind === kind);
}

/** The answer change confirming a suggestion makes, or null when it can't be placed automatically. */
export function answerChange(s: Suggestion, answers: Answers): [string, AnswerValue] | null {
  if (s.kind === "answer") return [s.field_id, s.value];
  const members = Array.isArray(answers[ROSTER_QUESTION]) ? answers[ROSTER_QUESTION] as HouseholdMember[] : [];
  const index = rosterIndex(members, s.person, answers);
  if (index < 0) return null;
  return [ROSTER_QUESTION, members.map((m, i) => i === index ? { ...m, gross_monthly_income: s.monthly_amount } : m)];
}

export function isApplied(s: Suggestion, answers: Answers): boolean {
  const change = answerChange(s, answers);
  return !!change && JSON.stringify(answers[change[0]]) === JSON.stringify(change[1]);
}

const money = (n: number) => `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
const PEOPLE: Record<HouseholdPerson, string> = { caregiver: "you", recipient: "", spouse: "a spouse", other_household_member: "another household member" };

export function describe(s: Suggestion, recipientName: string): string {
  if (s.kind === "member_income") return `${money(s.monthly_amount)} a month before deductions, for ${PEOPLE[s.person] || recipientName}`;
  const v = s.value;
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return v.join(", ");
  if (typeof v === "number" && s.field_id !== "tax.year") return money(v);
  return String(v);
}

/** The document's tax year when it differs from the year the caregiver chose. */
export function otherTaxYear(s: Suggestion, answers: Answers): number | null {
  if (s.kind !== "answer" || s.tax_year === null) return null;
  const chosen = Number(answers["tax.year"]);
  return Number.isInteger(chosen) && chosen > 0 && chosen !== s.tax_year ? s.tax_year : null;
}
