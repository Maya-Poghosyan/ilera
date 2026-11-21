import { expect, type Page, test } from "@playwright/test";

// Records against the real API and Postgres; the session is created through the app's own
// auth routes, with the verification email read from the test API's outbox.
const API = process.env.E2E_API_URL!;

async function signedInWithCase(page: Page) {
  const email = `records-${Date.now()}@example.test`;
  await page.request.post("/api/auth/signup", { data: { name: "Alex", email, phone: "5105550100", password: "correct horse" } });
  const mail: { kind: string; token?: string }[] = await (await page.request.get(`${API}/__e2e/mail/${email}`)).json();
  await page.request.post("/api/auth/verify-email", { data: { token: mail.at(-1)!.token } });
  const answers = await (await page.request.get(`${API}/__e2e/complete-intake`)).json();
  const caseId = (await (await page.request.post("/api/intake", { data: { answers } })).json()).id;
  expect((await page.request.patch("/api/auth/me", { data: { case_id: caseId } })).ok()).toBeTruthy();
}

test("a caregiver logs hours, tracks a renewal and reviews a possible fall", async ({ page }) => {
  await signedInWithCase(page);
  await page.goto("/dashboard/records");

  await page.getByRole("button", { name: "+ Entry" }).first().click();
  await page.getByLabel("Date", { exact: true }).fill("2026-11-02");
  await page.getByLabel("Total Hours").fill("3.5");
  await page.getByLabel("Activities (comma-separated)").fill("Bathing, meal prep");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("3.5 hrs")).toBeVisible();

  await page.getByRole("button", { name: "+ Renewal" }).click();
  await page.getByLabel("Program").fill("IHSS");
  await page.getByLabel("Due date").fill("2020-01-01");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("1 overdue")).toBeVisible();

  await page.getByRole("button", { name: "+ Entry" }).nth(1).click();
  await page.getByLabel("Date", { exact: true }).fill("2026-11-02");
  await page.getByLabel("Entry", { exact: true }).fill("Mom fell in the bathroom this morning but was not hurt.");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("Possible fall — needs review")).toBeVisible();

  await page.reload();
  await expect(page.getByText("3.5 hrs")).toBeVisible();
  await expect(page.getByText("1 journal entry mentions a possible fall")).toBeVisible();
  await page.getByRole("button", { name: "Not a fall" }).click();
  await expect(page.getByText("Not a fall", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("mentions a possible fall")).toHaveCount(0);
});
