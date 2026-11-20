// The document-reading API boundary: one request, its response parsed into typed suggestions.
// Mirrors backend/app/intake/documents/models.py.

export type HouseholdPerson = "caregiver" | "recipient" | "spouse" | "other_household_member";
export interface Source { page: number; evidence: string; as_of: string | null }
export interface AnswerSuggestion {
  kind: "answer";
  field_id: string;
  value: string | number | boolean | string[];
  tax_year: number | null;
  source: Source;
}
export interface IncomeSuggestion { kind: "member_income"; person: HouseholdPerson; monthly_amount: number; source: Source }
export type Suggestion = AnswerSuggestion | IncomeSuggestion;

export type ReadResult = { ok: true; suggestions: Suggestion[] } | { ok: false; message: string };

const MESSAGES: Record<string, string> = {
  too_large: "This file is too large.",
  unsupported_type: "Use a PDF, JPG or PNG file.",
  encrypted_pdf: "This PDF is password-protected. Save an unlocked copy and try again.",
  too_many_pages: "This PDF has too many pages. Upload just the pages you need.",
  unreadable: "We couldn't open this file.",
  no_text_layer: "This looks like a scanned PDF. Try a clear photo of the page instead.",
  unconfigured: "Reading documents isn't available yet. Please enter your answers.",
  rate_limited: "We're reading a lot of documents right now. Please try again later or enter your answers.",
};
const FALLBACK = "We couldn't read this document. Please enter your answers.";
const PEOPLE = new Set(["caregiver", "recipient", "spouse", "other_household_member"]);

function parseSource(x: unknown): Source | null {
  const s = x as Source;
  return s && Number.isInteger(s.page) && s.page > 0 && typeof s.evidence === "string" && (s.as_of === null || typeof s.as_of === "string") ? s : null;
}

/** Keep only well-formed suggestions; anything else is dropped rather than shown. */
export function parseSuggestions(body: unknown): Suggestion[] {
  const items = (body as { suggestions?: unknown })?.suggestions;
  if (!Array.isArray(items)) return [];
  return items.flatMap((item): Suggestion[] => {
    const source = parseSource(item?.source);
    if (!source) return [];
    if (item.kind === "member_income" && PEOPLE.has(item.person) && typeof item.monthly_amount === "number" && item.monthly_amount >= 0) {
      return [{ kind: "member_income", person: item.person, monthly_amount: item.monthly_amount, source }];
    }
    const v = item.value;
    const validValue = ["string", "number", "boolean"].includes(typeof v) || Array.isArray(v) && v.every((x: unknown) => typeof x === "string");
    if (item.kind === "answer" && typeof item.field_id === "string" && validValue && (item.tax_year === null || Number.isInteger(item.tax_year))) {
      return [{ kind: "answer", field_id: item.field_id, value: v, tax_year: item.tax_year, source }];
    }
    return [];
  });
}

export async function readDocument(file: Blob): Promise<ReadResult> {
  let res: Response;
  try {
    res = await fetch("/api/intake/documents", { method: "POST", headers: { "content-type": file.type || "application/octet-stream" }, body: file });
  } catch {
    return { ok: false, message: "We couldn't reach Ilera. Check your connection and try again." };
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const code = (body as { detail?: unknown })?.detail;
    return { ok: false, message: typeof code === "string" && MESSAGES[code] || FALLBACK };
  }
  return { ok: true, suggestions: parseSuggestions(body) };
}
