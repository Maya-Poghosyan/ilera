import { householdDetails, validHouseholdMembers } from "./household-data";
export { validHouseholdMembers, HOUSEHOLD_RELATIONSHIPS, HOUSEHOLD_TAX_LINKS } from "./household-data";
// Types + helpers for the schema-driven intake form. The schema itself is served
// by the backend at GET /api/intake/schema; this file mirrors its shape and
// implements show_when evaluation, [recipient name] interpolation, and validation.

export type FieldType =
  | "single_select"
  | "multi_select"
  | "number"
  | "short_text"
  | "long_text"
  | "state_dropdown"
  | "zip"
  | "date"
  | "boolean"
  | "household_members"
  | "program_statuses"
  | "program_dates"
  | "tag_input";

export interface Validation {
  exclusive_options?: string[];
  incompatible_options?: string[][];
  min?: number;
  max?: number;
  integer?: boolean;
}

export type Condition =
  | { field: string; op: string; value?: unknown }
  | { any: Condition[] }
  | { all: Condition[] }
  | { not: Condition };

export interface Question {
  field_id: string;
  text: string;
  type: FieldType;
  required: boolean;
  options?: string[];
  option_labels?: Record<string, string>;
  answer_aliases?: Record<string, string | null>;
  display_as?: "dropdown";
  hide_title?: boolean;
  page_group?: string;
  page_title?: string;
  page_helper_text?: string;
  page_helper_link?: { text: string; href: string };
  placeholder?: string;
  helper_text?: string;
  helper_link?: { text: string; href: string };
  helper_links?: { text: string; href: string }[];
  why_this_matters?: string;
  show_when?: Condition;
  validation?: Validation;
  allow_not_sure?: boolean;
  allow_prefer_not_to_answer?: boolean;
  alt_ui?: string;
  system_behavior?: string;
  group?: string;
  layout?: string;
}

export interface Screen {
  id: string;
  title: string;
  intro_text?: string;
  intro_emphasis?: string;
  questions: Question[];
}

export interface IntakeSchema {
  version: string;
  welcome: { header: string; body: string; button: string };
  submit_button: string;
  name_field: string;
  name_fallback: string;
  form_wide_rules: string[];
  delayed_questions: string[];
  screens: Screen[];
}

export interface HouseholdMember {
  kind: "recipient" | "spouse" | "caregiver" | "other";
  relationship: string;
  age: number | string | null;
  lives_with_recipient: boolean | string | null;
  tax_link: string;
  employment_status: string;
  gross_monthly_income: number | string | null;
  income_sources: string[];
  income_other: string;
  income_varies: string;
}
export type ProgramAnswers = Record<string, string>;
export type AnswerValue = string | string[] | HouseholdMember[] | ProgramAnswers | number | boolean | null;
export type Answers = Record<string, AnswerValue>;

export const NOT_SURE = "I'm not sure";
export const PREFER_NOT = "Prefer not to answer";

function toNumber(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v);
  return null;
}

// Evaluate a machine-readable show_when / trigger condition against the answers.
export function evalCondition(cond: Condition | undefined, answers: Answers): boolean {
  if (!cond) return true;
  if ("any" in cond) return cond.any.some((c) => evalCondition(c, answers));
  if ("all" in cond) return cond.all.every((c) => evalCondition(c, answers));
  if ("not" in cond) return !evalCondition(cond.not, answers);

  const raw = answerContext(answers)[cond.field];
  const value = cond.value;
  switch (cond.op) {
    case "equals":
      return raw === value;
    case "not_equals":
      return raw !== value;
    case "in":
      return Array.isArray(value) && value.includes(raw as never);
    case "includes":
      return Array.isArray(raw) && raw.some((item) => item === value);
    case "includes_any":
      return (
        Array.isArray(raw) &&
        Array.isArray(value) &&
        (value as string[]).some((v) => raw.some((item) => item === v))
      );
    case "gte": {
      const n = toNumber(raw);
      return n !== null && n >= (value as number);
    }
    case "lte": {
      const n = toNumber(raw);
      return n !== null && n <= (value as number);
    }
    case "gt": {
      const n = toNumber(raw);
      return n !== null && n > (value as number);
    }
    case "lt": {
      const n = toNumber(raw);
      return n !== null && n < (value as number);
    }
    case "answered":
      return raw !== undefined && raw !== null && raw !== "" && !(Array.isArray(raw) && raw.length === 0);
    case "blank":
      return raw === undefined || raw === null || raw === "" || (Array.isArray(raw) && raw.length === 0);
    default:
      return false;
  }
}

// Replace [recipient name] (any casing) with the preferred name or a fallback.
export function interpolateName(text: string, name: string): string {
  return text.replace(/\[recipient name\]/gi, name);
}

export function recipientName(answers: Answers, schema: IntakeSchema): string {
  const v = answers[schema.name_field];
  if (typeof v === "string" && v.trim()) return v.trim();
  return schema.name_fallback;
}

// Effective option list for a select question, injecting the form-wide
// "I'm not sure" / "Prefer not to answer" options where the schema marks them
// and they are not already present.
export function effectiveOptions(q: Question): string[] {
  const opts = [...(q.options ?? [])];
  if (q.allow_not_sure && !opts.includes(NOT_SURE)) opts.push(NOT_SURE);
  if (q.allow_prefer_not_to_answer && !opts.includes(PREFER_NOT)) opts.push(PREFER_NOT);
  return opts;
}

export function isAnswered(value: AnswerValue): boolean {
  if (value === undefined || value === null) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "string") return value.trim() !== "";
  return true;
}

// Validate every visible value, including optional answers and numeric bounds.
export function validateQuestions(questions: Question[], answers: Answers): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const q of questions) {
    const v = answers[q.field_id];
    if (!isAnswered(v)) {
      if (q.required) errors[q.field_id] = "Please answer or choose an available unsure option.";
      continue;
    }
    if (typeof v === "string" && ((v === NOT_SURE && q.allow_not_sure) || (v === PREFER_NOT && q.allow_prefer_not_to_answer))) continue;
    if (q.type === "program_statuses" || q.type === "program_dates") {
      const programs = answers["recipient.programs_touched"];
      if (!Array.isArray(programs) || !programs.length || typeof v !== "object" || v === null || Array.isArray(v) || Object.keys(v).sort().join("|") !== [...programs].sort().join("|") || Object.values(v).some(entry => typeof entry !== "string" || (q.type === "program_statuses" ? !q.options?.includes(entry) : entry !== NOT_SURE && !validDate(entry)))) errors[q.field_id] = "Complete the details for each selected program.";
      continue;
    }
    const options = effectiveOptions(q);
    if (q.type === "household_members") {
      if (!validHouseholdMembers(v, answers)) errors[q.field_id] = "Complete each person’s details, use unsure where needed, or remove an extra person.";
      continue;
    }
    if (typeof v === "string" && (v === NOT_SURE || v === PREFER_NOT) && !options.includes(v)) {
      errors[q.field_id] = "Choose an available unsure option.";
      continue;
    }
    if (q.type === "single_select" && (typeof v !== "string" || !options.includes(v))) errors[q.field_id] = "Choose one of the available answers.";
    if (q.type === "multi_select" || q.type === "tag_input") {
      if (!Array.isArray(v) || v.some((item) => typeof item !== "string" || !item.trim()) || (q.type === "multi_select" && v.some((item) => typeof item !== "string" || !options.includes(item)))) {
        errors[q.field_id] = "Choose valid answers.";
        continue;
      }
      const selections = v as string[];
      if (new Set(selections).size !== selections.length || (selections.length > 1 && selections.some((item) => q.validation?.exclusive_options?.includes(item)))) errors[q.field_id] = "Choose an unsure or none answer on its own.";
      if (q.validation?.incompatible_options?.some(pair => pair.every(item => selections.includes(item)))) errors[q.field_id] = "Choose either no health coverage or the active coverage types.";
    }
    if (q.type === "number") {
      if (typeof v !== "number" || !Number.isFinite(v) || (q.validation?.integer && !Number.isInteger(v)) || v < (q.validation?.min ?? -Infinity) || v > (q.validation?.max ?? Infinity)) errors[q.field_id] = "Enter a valid number within the shown limits.";
    }
    if (q.type === "boolean" && typeof v !== "boolean") errors[q.field_id] = "Choose Yes or No.";
    if (q.type === "zip" && (typeof v !== "string" || !/^\d{5}$/.test(v))) errors[q.field_id] = "Enter a five-digit ZIP code.";
    if (q.type === "state_dropdown" && (typeof v !== "string" || !(q.options ?? US_STATES).includes(v))) errors[q.field_id] = "Choose a state.";
    if (q.type === "date" && (typeof v !== "string" || !validDate(v) || (["recipient.date_of_birth", "caregiver.date_of_birth", "recipient.lpr_since"].includes(q.field_id) && v > localDate()))) errors[q.field_id] = "Enter a valid date.";
    if ((q.type === "short_text" || q.type === "long_text") && typeof v !== "string") errors[q.field_id] = "Enter text.";
  }
  return errors;
}

function localDate(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  return parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day;
}

export function answerContext(answers: Answers, today = new Date()): Answers {
  const context = { ...answers };
  for (const prefix of ["recipient", "caregiver"]) {
    delete context[`${prefix}.age`];
    const birth = answers[`${prefix}.date_of_birth`];
    if (typeof birth === "string" && validDate(birth) && birth <= localDate(today)) {
      const [year, month, day] = birth.split("-").map(Number);
      context[`${prefix}.age`] = today.getFullYear() - year - (today.getMonth() + 1 < month || (today.getMonth() + 1 === month && today.getDate() < day) ? 1 : 0);
    }
  }
  Object.assign(context, householdDetails(answers));
  const filing = answers['recipient.tax_filing_status'];
  context['tax.recipient_joint_return'] = filing === 'Yes, jointly with a spouse' ? 'Yes' : filing === 'Yes, their own return' || filing === 'No' ? 'No' : null;
  if (answers['caregiver.claims_recipient'] === true) {
    context['recipient.claimed_as_dependent'] = 'Yes';
    context['recipient.dependent_claimant_relationship'] = ({ Parent: 'Adult child', Child: 'Parent', 'Spouse or domestic partner': 'Spouse', 'Parent-in-law': 'Other relative', Sibling: 'Other relative', Grandparent: 'Other relative', Grandchild: 'Other relative', 'Other relative': 'Other relative', Friend: 'Someone else', Neighbor: 'Someone else', Other: 'Someone else' } as Record<string, string>)[String(answers['caregiver.relationship'])] ?? null;
  }
  const combined = answers["recipient.coverage_and_benefits"];
  if (Array.isArray(combined)) {
    const cov = ["Medicaid", "Medicare", "VA health care", "Employer or private insurance", "No health coverage", "Other"];
    context["recipient.health_coverage"] = combined.filter(x => typeof x === 'string' && (cov.includes(x) || x === NOT_SURE)) as string[];
    context["recipient.current_benefits"] = combined.filter(x => typeof x === 'string' && !cov.includes(x)) as string[];
  }
  context["recipient.medicaid_status"] = answers["recipient.medicaid_covered"] === true ? "Enrolled now" : null;
  if (answers["caregiver.coresidence"] === "Yes") {
    for (const part of ["street", "city", "state", "county", "zip"]) context[`recipient.address.${part}`] = answers[`caregiver.address.${part}`];
  }
  return context;
}

export function cleanAnswers(schema: IntakeSchema, answers: Answers): Answers {
  const questions = schema.screens.flatMap((screen) => screen.questions);
  const known = new Set(questions.map((q) => q.field_id));
  let result = Object.fromEntries(Object.entries(answers).filter(([key]) => known.has(key))) as Answers;
  for (const q of questions) {
    const value = result[q.field_id];
    if (Array.isArray(value) && q.answer_aliases) {
      const aliases = q.answer_aliases;
      result[q.field_id] = [...new Set(value.filter((item): item is string => typeof item === "string").map(item => Object.hasOwn(aliases, item) ? aliases[item] : item).filter((item): item is string => item !== null))];
    }
    if (typeof value === "string" && q.answer_aliases && Object.hasOwn(q.answer_aliases, value)) {
      const replacement = q.answer_aliases[value];
      if (replacement === null) delete result[q.field_id];
      else result[q.field_id] = replacement;
    }
  }
  const members = result["household.members"];
  if (Array.isArray(members)) result["household.members"] = members.filter(m => {
    if (!m || typeof m !== 'object') return true;
    if (m.kind === 'spouse' && result['recipient.marital_status'] !== 'Yes') return false;
    if (m.kind === 'caregiver' && result['recipient.marital_status'] === 'Yes' && result['caregiver.relationship'] === 'Spouse or domestic partner') return false;
    return true;
  }) as HouseholdMember[];
  const programs = result['recipient.programs_touched'];
  for (const key of ['recipient.program_statuses', 'case.program_dates']) {
    const rows = result[key];
    if (rows && typeof rows === 'object' && !Array.isArray(rows)) result[key] = Object.fromEntries(Object.entries(rows).filter(([program]) => Array.isArray(programs) && programs.includes(program as never)));
  }
  const combined = result['recipient.coverage_and_benefits'];
  if (result['recipient.medicaid_covered'] === true) {
    if (!Array.isArray(combined)) result['recipient.coverage_and_benefits'] = ['Medicaid'];
    else if (!combined.includes('Medicaid' as never)) result['recipient.coverage_and_benefits'] = [...combined.filter(x => x !== NOT_SURE), 'Medicaid'] as string[];
  }
  while (true) {
    const active = Object.fromEntries(Object.entries(result).filter(([key]) => evalCondition(questions.find((q) => q.field_id === key)?.show_when, result))) as Answers;
    if (Object.keys(active).length === Object.keys(result).length) return active;
    result = active;
  }
}

export const US_STATES: string[] = [
  "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID",
  "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO",
  "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
  "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
];
