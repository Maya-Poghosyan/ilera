import { expect, type APIRequestContext, type Page, test } from "@playwright/test";

// The core journey against the real web app, real API and Postgres. Only outside services are
// replaced (see backend/tests/e2e_api.py): email is captured, the eligibility pipeline isn't run.
const API = process.env.E2E_API_URL!;

async function lastMail(request: APIRequestContext, address: string, kind: "verify" | "otp") {
  const messages: { kind: string; token?: string; code?: string }[] = await (await request.get(`${API}/__e2e/mail/${address}`)).json();
  const found = messages.filter(m => m.kind === kind).at(-1);
  expect(found, `no ${kind} email for ${address}`).toBeTruthy();
  return found!;
}

async function submitIntake(page: Page, request: APIRequestContext) {
  const answers = await (await request.get(`${API}/__e2e/complete-intake`)).json();
  await page.goto("/intake");
  await page.evaluate(draft => localStorage.setItem("ilera_intake_draft", draft), JSON.stringify({ answers, questionId: null, review: true }));
  await page.reload();
  await page.getByRole("button", { name: "Continue saved progress" }).click();
  await expect(page.getByRole("heading", { name: "Ready to submit" })).toBeVisible();
  await page.getByRole("button", { name: "Find possible programs" }).click();
  await expect(page).toHaveURL(/\/eligibility\/[\w-]+$/);
  await expect(page.getByRole("heading", { name: "Determining eligibility…" })).toBeVisible();
  return page.url().split("/").pop()!;
}

test("a caregiver submits intake, creates an account and keeps reminders across devices", async ({ page, request, browser }) => {
  const email = `caregiver-${Date.now()}@example.test`;
  const password = "correct horse battery";
  const caseId = await submitIntake(page, request);

  // Signup claims the anonymous case; the emailed link activates the account.
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("Alex Caregiver");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Phone number").fill("5105550100");
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /create|sign up/i }).click();
  await expect(page.getByText("Check your email")).toBeVisible();
  const { token } = await lastMail(request, email, "verify");
  await page.goto(`/verify-email?token=${token}`);
  await expect(page).toHaveURL(/\/get-started$/);
  await expect(page.getByText("You can also connect your email inboxes later on the Care Calendar page.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect Gmail" })).toBeVisible();
  // The account now owns the case submitted before signup.
  await expect(page.locator(`a[href="/eligibility/${caseId}"]`, { hasText: "See my results" })).toBeVisible();

  // A reminder saved on the dashboard survives a reload.
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "+ Reminder" }).click();
  await page.getByLabel("Message").fill("Refill blood pressure medication");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByText("Refill blood pressure medication")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Refill blood pressure medication")).toBeVisible();

  // On a new device: password, then the emailed one-time code, then the same dashboard.
  const other = await (await browser.newContext()).newPage();
  await other.goto("/login");
  await other.getByLabel("Email").fill(email);
  await other.getByLabel("Password").fill(password);
  await other.getByRole("button", { name: /sign in|log in|continue/i }).click();
  await expect(other.getByLabel("Login code")).toBeVisible();
  const { code } = await lastMail(request, email, "otp");
  await other.getByLabel("Login code").fill(code!);
  await other.getByRole("button", { name: /verify|sign in|continue/i }).click();
  // Signed in once the app moves on from the login page (it sets the session first).
  await other.waitForURL(url => !url.pathname.startsWith("/login"));
  await other.goto("/dashboard");
  await expect(other.getByText("Refill blood pressure medication")).toBeVisible();
});

test("an account cannot sign in until its email is verified", async ({ page, request }) => {
  const email = `unverified-${Date.now()}@example.test`;
  await request.post(`${API}/api/auth/signup`, { data: { name: "Pat", email, phone: "", password: "secret-pass" } });
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("secret-pass");
  await page.getByRole("button", { name: /sign in|log in|continue/i }).click();
  await expect(page.getByText("Please verify your email address before signing in")).toBeVisible();
});
