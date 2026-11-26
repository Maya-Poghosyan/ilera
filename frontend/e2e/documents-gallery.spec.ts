import { resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { signedInWithCase } from "./helpers";

test("Documents shows uploaded files and preserves their previews after reload", async ({ page }) => {
  await signedInWithCase(page);
  await page.goto("/dashboard/documents");
  await expect(page.getByText("No documents uploaded yet.")).toBeVisible();

  const pdf = resolve("../backend/data/forms/CDSS/IHSS/SOC-295.pdf");
  await page.getByLabel("Upload files").setInputFiles(pdf);
  const gallery = page.getByRole("list", { name: "Uploaded documents" });
  const file = gallery.getByRole("link", { name: "Download SOC-295.pdf" });
  await expect(file.locator("img")).toBeVisible();
  await expect(file.getByText("SOC-295.pdf")).toBeVisible();

  await page.getByLabel("Upload files").setInputFiles({
    name: "receipt.png",
    mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6lxbZsAAAAASUVORK5CYII=", "base64"),
  });
  const image = gallery.getByRole("link", { name: "Download receipt.png" }).locator("img");
  await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBe(1);

  await page.reload();
  await expect(file.locator("img")).toBeVisible();
  const download = page.waitForEvent("download");
  await file.click();
  expect((await download).suggestedFilename()).toBe("SOC-295.pdf");
  page.once("dialog", (dialog) => dialog.accept());
  await gallery.getByRole("button", { name: "Remove SOC-295.pdf" }).click();
  await expect(file).toHaveCount(0);
  page.once("dialog", (dialog) => dialog.accept());
  await gallery.getByRole("button", { name: "Remove receipt.png" }).click();
  await expect(page.getByText("No documents uploaded yet.")).toBeVisible();
});
