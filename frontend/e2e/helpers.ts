import { expect, type Page } from "@playwright/test";

export const API = process.env.E2E_API_URL!;

/** A verified, signed-in caregiver whose account owns a completed intake. Returns the case id. */
export async function signedInWithCase(page: Page): Promise<string> {
  const email = `caregiver-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@example.test`;
  await page.request.post("/api/auth/signup", { data: { name: "Alex", email, phone: "5105550100", password: "correct horse" } });
  const mail: { kind: string; token?: string }[] = await (await page.request.get(`${API}/__e2e/mail/${email}`)).json();
  await page.request.post("/api/auth/verify-email", { data: { token: mail.at(-1)!.token } });
  const answers = await (await page.request.get(`${API}/__e2e/complete-intake`)).json();
  const caseId: string = (await (await page.request.post("/api/intake", { data: { answers } })).json()).id;
  expect((await page.request.patch("/api/auth/me", { data: { case_id: caseId } })).ok()).toBeTruthy();
  return caseId;
}
