import { expect, test } from "@playwright/test";

import { API, signedInWithCase } from "./helpers";

test("an eligible program opens its form questions and returns to the list", async ({ page }) => {
  const caseId = await signedInWithCase(page);
  await page.request.post(`${API}/__e2e/cases/${caseId}/eligible/IHSS`);

  await page.goto("/dashboard/applications");
  await expect(page.getByText("IHSS", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Fill forms" }).click();

  await expect(page.getByRole("heading", { name: "IHSS" })).toBeVisible();
  await expect(page.getByText(/Filled \d+ of \d+ fields automatically/)).toBeVisible();
  await expect(page.getByText(/^Step 1 of \d+$/)).toBeVisible();

  await page.getByRole("button", { name: "← Back to applications" }).click();
  await expect(page.getByRole("heading", { name: "Your applications" })).toBeVisible();
});
