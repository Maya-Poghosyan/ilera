import { expect, type Page, test } from "@playwright/test";

import { API, signedInWithCase } from "./helpers";

// Gmail against the real web app, API, Postgres and email worker code. Google sign-in and the
// Gmail API are a local stand-in (e2e/fake-google.mjs); see backend/tests/e2e_api.py.
const GOOGLE = "http://127.0.0.1:4518";
const GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly";

/** Stand in for Google's sign-in page: register a code for `address`, then send the browser back
 * to the app's callback the way Google would. `scope` is what the caregiver left ticked. */
async function googleSignsIn(page: Page, baseURL: string, address: string, scope?: string) {
  await page.route("https://accounts.google.com/**", async route => {
    const asked = new URL(route.request().url()).searchParams;
    expect(asked.get("scope")).toContain(GMAIL_SCOPE);
    expect(asked.get("access_type")).toBe("offline");
    const code = `code-${crypto.randomUUID()}`;
    await page.request.post(`${GOOGLE}/__codes`, {
      data: { code, email: address, nonce: asked.get("nonce"), challenge: asked.get("code_challenge"), scope },
    });
    const back = new URL("/api/email/google/callback", baseURL);
    back.searchParams.set("state", asked.get("state")!);
    back.searchParams.set("code", code);
    await route.fulfill({ status: 302, headers: { location: back.href } });
  });
}

test("a caregiver connects Gmail, a new email becomes a suggestion to review, and disconnecting revokes access", async ({ page, baseURL }) => {
  await signedInWithCase(page);
  const address = `caregiver${Date.now()}@gmail.test`;
  // Mail from before the connection stays unread.
  await page.request.post(`${GOOGLE}/__mail`, { data: { email: address, id: "old-1", ageSeconds: 86_400,
    from: "IHSS <ihss@county.example>", subject: "Earlier notice", body: "IHSSVISIT on an older date" } });
  await googleSignsIn(page, baseURL!, address);

  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Connect Gmail" }).click();
  await expect(page.getByText("Gmail connected.")).toBeVisible();
  await expect(page.getByText(`${address} · Connected`)).toBeVisible();

  // A county notice arrives; the hourly pass finds it and the worker reads it.
  await page.request.post(`${GOOGLE}/__mail`, { data: { email: address, id: "new-1",
    from: "IHSS <ihss@county.example>", subject: "Your IHSS reassessment",
    body: "IHSSVISIT A social worker will visit on December 8, 2026 at 10:00 AM Pacific." } });
  expect(await (await page.request.post(`${API}/__e2e/email/maintain`)).json())
    .toMatchObject({ checked: 1, enqueued: 1, failed: 0 });
  expect(await (await page.request.post(`${API}/__e2e/email/scan`)).json()).toEqual(["suggested"]);

  await page.reload();
  await expect(page.getByText("IHSS reassessment visit")).toBeVisible();
  await expect(page.getByText("From email")).toBeVisible();

  // The next pass overlaps the last by a second, so a just-read email can be listed again; the
  // worker's ledger keeps it from being read twice.
  expect(await (await page.request.post(`${API}/__e2e/email/maintain`)).json()).toMatchObject({ checked: 1, failed: 0 });
  for (const outcome of await (await page.request.post(`${API}/__e2e/email/scan`)).json()) expect(outcome).toBe("duplicate");
  await page.reload();
  await expect(page.getByText("IHSS reassessment visit")).toHaveCount(1);

  await page.getByRole("button", { name: "Disconnect" }).click();
  await expect(page.getByText("Gmail disconnected and saved credentials deleted.")).toBeVisible();
  await expect(page.getByText(`${address} · Connected`)).toHaveCount(0);
  expect(await (await page.request.get(`${GOOGLE}/__revoked`)).json()).toContain(address);
});

test("Gmail doesn't connect when the caregiver unticks mail access on Google's consent screen", async ({ page, baseURL }) => {
  await signedInWithCase(page);
  const address = `caregiver${Date.now()}@gmail.test`;
  await googleSignsIn(page, baseURL!, address, "openid https://www.googleapis.com/auth/userinfo.email");

  await page.goto("/dashboard");
  await page.getByRole("button", { name: "Connect Gmail" }).click();
  await expect(page.getByText("Gmail could not connect. Please sign in and try again.")).toBeVisible();
  await expect(page.getByText(address)).toHaveCount(0);
});
