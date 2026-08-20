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
  | "tag_input";

export interface Validation {
  exclusive_options?: string[];
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
  helper_text?: string;
  helper_link?: { text: string; href: string };
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
  questions: Question[];
}

export interface MiniModule {
  id: string;
  title: string;
  trigger: Condition;
  routing: string[];
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
  contact_screen: Screen;
  mini_modules: MiniModule[];
}

export type AnswerValue = string | string[] | number | boolean | null;
export type Answers = Record<string, AnswerValue>;

export const NOT_SURE = "I'm not sure";
export const PREFER_NOT = "Prefer not to answer";

function toNumber(v: unknown): number | null {
  if (typeof v === "number") return v;
  if (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v))) return Number(v);
  return null;
}

// Evaluate a machine-readable show_when / trigger condition against the answers.
export function evalCondition(cond: Condition | undefined, answers: Answers): boolean {
  if (!cond) return true;
  if ("any" in cond) return cond.any.some((c) => evalCondition(c, answers));
  if ("all" in cond) return cond.all.every((c) => evalCondition(c, answers));
  if ("not" in cond) return !evalCondition(cond.not, answers);

  const raw = answers[cond.field];
  const value = cond.value;
  switch (cond.op) {
    case "equals":
      return raw === value;
    case "not_equals":
      return raw !== value;
    case "in":
      return Array.isArray(value) && value.includes(raw as never);
    case "includes":
      return Array.isArray(raw) && raw.includes(value as string);
    case "includes_any":
      return (
        Array.isArray(raw) &&
        Array.isArray(value) &&
        (value as string[]).some((v) => raw.includes(v))
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

// Validate the visible required questions on a screen. Returns map of field_id -> error.
export function validateQuestions(questions: Question[], answers: Answers): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const q of questions) {
    const v = answers[q.field_id];
    if (q.required && !isAnswered(v)) {
      errors[q.field_id] = "This question is required.";
      continue;
    }
    const exclusive = q.validation?.exclusive_options;
    if (exclusive && Array.isArray(v)) {
      const picked = v as string[];
      const hasExclusive = exclusive.some((e) => picked.includes(e));
      if (hasExclusive && picked.length > 1) {
        errors[q.field_id] = `"${exclusive.join('", "')}" cannot be combined with other answers.`;
      }
    }
  }
  return errors;
}

export const US_STATES: string[] = [
  "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID",
  "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO",
  "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA",
  "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
];
