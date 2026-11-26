import { expect, test } from "@playwright/test";

import { API, signedInWithCase } from "./helpers";

test("an application can be marked pending, archived, restored, and accepted", async ({ page }) => {
  const caseId = await signedInWithCase(page);
  await page.request.post(`${API}/__e2e/cases/${caseId}/eligible/IHSS`);

  await page.goto("/dashboard/applications");
  await expect(page.getByText("IHSS", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Open IHSS application" }).click();

  await expect(page.getByRole("heading", { name: "IHSS" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Update Information" })).toBeVisible();
  await expect(page.getByText(/^Questions 1 of \d+$/)).toBeVisible();

  await page.getByRole("button", { name: "Update status", exact: true }).click();
  await page.getByRole("button", { name: "Mark pending determination" }).click();
  await expect(page.getByRole("heading", { name: "Program Applications" })).toBeVisible();

  const open = page.getByRole("button", { name: "Open IHSS application" });
  await open.click();
  await expect(page.getByRole("heading", { name: "Update application status" })).toBeVisible();
  await expect(page.getByText("Pending determination", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Archive application" }).click();
  await expect(open).toHaveCount(0);
  await page.getByRole("button", { name: "Archived", exact: true }).click();
  await open.click();
  await page.getByRole("button", { name: "Restore application" }).click();
  await expect(open).toHaveCount(0);
  await page.getByRole("button", { name: "Likely matches", exact: true }).click();
  await open.click();
  await expect(page.getByText("Pending determination", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Mark accepted" }).click();
  await page.getByLabel("Approval date (optional)").fill("2026-10-28");
  await page.getByLabel("Next renewal or review deadline (optional)").fill("2027-10-28");
  await page.getByRole("button", { name: "Save approval" }).click();
  await expect(page.getByText("Accepted", { exact: true })).toBeVisible();
  await open.click();
  await page.getByRole("link", { name: "View records" }).click();
  await expect(page.getByText("IHSS", { exact: true })).toBeVisible();
});
