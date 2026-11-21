import { expect, test } from "@playwright/test";

import { signedInWithCase } from "./helpers";

// Records against the real API and Postgres.
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
