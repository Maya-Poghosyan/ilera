// Intake runs before the user has an account, so the case it creates is parked
// here until they sign up (or sign in) and it can be attached to their profile.
const PENDING_KEY = "ilera_pending_case_id";

export function setPendingCaseId(caseId: string): void {
  localStorage.setItem(PENDING_KEY, caseId);
}

export function getPendingCaseId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(PENDING_KEY);
}

export function clearPendingCaseId(): void {
  localStorage.removeItem(PENDING_KEY);
}
