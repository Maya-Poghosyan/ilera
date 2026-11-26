import { expect, test } from "@playwright/test";

import { API, signedInWithCase } from "./helpers";

test("an application can be marked pending, archived, restored, and accepted", async ({ page }) => {
  const caseId = await signedInWithCase(page);
  await page.request.post(`${API}/__e2e/cases/${caseId}/eligible/IHSS`);

  await page.goto("/dashboard/applications");
  await expect(page.getByText(/^IHSS\s*Official website/)).toBeVisible();
  await page.getByRole("button", { name: "Open IHSS application" }).click();

  await expect(page.getByRole("heading", { name: "IHSS" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Update Information" })).toBeVisible();
  await expect(page.getByText(/^Questions 1 of \d+$/)).toBeVisible();
  await expect(page.getByRole("button", { name: /^Previous step/ })).toHaveCount(0);
  // The next-step arrow needs every required answer first.
  await page.getByRole("button", { name: "Next step: Gather documents" }).click();
  await expect(page.getByRole("heading", { name: "Update Information" })).toBeVisible();

  // Skip ahead to follow-up, where the next step is the status update.
  await page.getByRole("button", { name: "Back to applications" }).click();
  expect((await page.request.put(`/api/applications/${caseId}/IHSS/progress`, { data: { stage: "follow_up" } })).ok()).toBe(true);
  await page.reload();
  await page.getByRole("button", { name: "Open IHSS application" }).click();
  await expect(page.getByRole("heading", { name: "Follow-up Steps" })).toBeVisible();
  await page.getByRole("button", { name: "Next step: Update status" }).click();
  await expect(page.getByRole("heading", { name: "Update status" })).toBeVisible();
  await page.getByRole("button", { name: "Previous step: Follow-up Steps" }).click();
  await expect(page.getByRole("heading", { name: "Follow-up Steps" })).toBeVisible();
  await page.getByRole("button", { name: "Previous step: Review application forms" }).click();
  await expect(page.getByTitle("Filled application forms")).toBeVisible();
  await page.getByRole("button", { name: "Next step: Follow-up Steps" }).click();
  await page.getByRole("button", { name: "Next step: Update status" }).click();
  await page.getByRole("button", { name: "Mark pending determination" }).click();
  await expect(page.getByRole("heading", { name: "Program Applications" })).toBeVisible();

  const open = page.getByRole("button", { name: "Open IHSS application" });
  await open.click();
  await expect(page.getByRole("heading", { name: "Update status" })).toBeVisible();
  await expect(page.getByText("Pending determination", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Archive application" }).click();
  const archived = page.getByRole("button", { name: /^Archived/ });
  await expect(archived).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#applications-likely")).toHaveText("No likely matches.");
  await archived.click();
  await expect(open).toHaveCount(0);
  await archived.click();
  await open.click();
  await page.getByRole("button", { name: "Restore application" }).click();
  await expect(page.locator("#applications-archived")).toHaveText("No archived applications.");
  await expect(page.getByRole("link", { name: /Official website for IHSS/ })).toHaveAttribute("href", /cdss\.ca\.gov/);
  await open.click();
  await expect(page.getByText("Pending determination", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Mark approved" }).click();
  await page.getByLabel("Approval date (optional)").fill("2026-10-28");
  await page.getByLabel("Next renewal or review deadline (optional)").fill("2027-10-28");
  await page.getByRole("button", { name: "Save approval" }).click();
  await expect(page.getByText(/^IHSS \(approved\)\s*Official website/)).toBeVisible();
  await open.click();
  await page.getByRole("link", { name: "View records" }).click();
  await expect(page.getByText("IHSS", { exact: true })).toBeVisible();
});
