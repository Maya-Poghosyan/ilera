import type { Answers } from "@/features/intake/schema";

// Responses and the current card are saved automatically on this browser.
const DRAFT_KEY = "ilera_intake_draft";

export interface Draft {
  answers: Answers;
  questionId: string | null;
  version?: string;
  review?: boolean;
}

export function readDraft(): Draft | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const draft = JSON.parse(raw) as Draft;
    if (!draft.answers || Object.keys(draft.answers).length === 0) return null;
    return { answers: draft.answers, questionId: draft.questionId ?? null, version: draft.version, review: draft.review === true };
  } catch {
    return null;
  }
}

/** Saves a draft with answers, clears an empty one. Throws when storage is unavailable. */
export function writeDraft(draft: Draft): "saved" | "cleared" {
  if (Object.keys(draft.answers).length) {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    return "saved";
  }
  localStorage.removeItem(DRAFT_KEY);
  return "cleared";
}

/** Throws when storage is unavailable. */
export function clearDraft(): void {
  localStorage.removeItem(DRAFT_KEY);
}
