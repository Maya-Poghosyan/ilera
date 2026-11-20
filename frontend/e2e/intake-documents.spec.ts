import { expect, type Page, test } from "@playwright/test";

// A one-page PDF whose text layer holds `text` (the stand-in model keys its reply off a marker word).
function pdf(text: string): Buffer {
  const stream = `BT /F1 12 Tf 72 720 Td (${text}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let out = "%PDF-1.4\n";
  const offsets = objects.map((body, i) => { const at = out.length; out += `${i + 1} 0 obj\n${body}\nendobj\n`; return at; });
  const xref = out.length;
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.map(o => `${String(o).padStart(10, "0")} 00000 n \n`).join("")}`;
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}
// Real documents have a text layer well past the backend's scanned-PDF threshold.
const FILLER = " Statement prepared for the account holder. Keep for your records.";
const file = (name: string, text: string) => ({ name, mimeType: "application/pdf", buffer: pdf(text && text + FILLER) });

const member = (kind: string, relationship: string, patch = {}) => ({
  kind, relationship, age: 50, lives_with_recipient: true, tax_link: "Neither", employment_status: "Employed full time",
  income_sources: ["Wages"], gross_monthly_income: 1000, income_other: "", income_varies: "No", ...patch,
});
const BASE = {
  "recipient.first_name": "Rosa",
  "caregiver.relationship": "Parent",
  "caregiver.coresidence": "Yes",
  "caregiver.employment_status": "Employed full time",
  "caregiver.caregiving_employment_impact": ["Taking leave"],
  "recipient.marital_status": "No",
  "household.members": [member("recipient", "Self", { age: 80, employment_status: "Retired" }), member("caregiver", "Child")],
};

/** Resume a saved intake at a section's title card. */
async function startAt(page: Page, section: string, answers: Record<string, unknown> = {}) {
  await page.addInitScript(draft => localStorage.setItem("ilera_intake_draft", draft),
    JSON.stringify({ answers: { ...BASE, ...answers }, questionId: `section:${section}` }));
  await page.goto("/intake");
  await page.getByRole("button", { name: "Continue saved progress" }).click();
}

async function upload(page: Page, ...files: { name: string; mimeType: string; buffer: Buffer }[]) {
  await page.getByLabel("Document files").setInputFiles(files);
}

/** Click Next/Continue until the question is on screen. */
async function advanceTo(page: Page, fieldId: string) {
  const question = page.locator(`[data-field-id="${fieldId}"]`);
  for (let i = 0; i < 40 && !(await question.isVisible()); i++) {
    await page.getByRole("button", { name: /^(Next|Continue)$/ }).click();
  }
  await expect(question).toBeVisible();
}

const panel = (page: Page) => page.getByRole("region", { name: "Suggestions from your documents" });

test("a paystub fills answers in two sections only after the caregiver confirms", async ({ page }) => {
  await startAt(page, "work_caregiving");
  await expect(page.getByText("Add documents (optional)")).toBeVisible();
  await upload(page, file("october-stub.pdf", "PAYSTUB Gross pay 2,000.00 CA SDI 24.00"));
  await expect(page.getByText("2 suggested answers to review in the questions ahead")).toBeVisible();

  await advanceTo(page, "caregiver.sdi_deductions");
  const sdi = page.locator('[data-field-id="caregiver.sdi_deductions"]');
  await expect(sdi.getByRole("button", { name: "Yes", pressed: true })).toHaveCount(0);
  await expect(panel(page)).toContainText("“october-stub.pdf”, page 1, 2026-10-31");
  await expect(panel(page)).toContainText("Deductions: CA SDI line");
  await panel(page).getByRole("button", { name: "Use this answer" }).click();
  await expect(sdi.getByRole("button", { name: "Yes", pressed: true })).toBeVisible();
  await expect(panel(page)).toContainText("Answer filled in");

  // The same document's income reaches the household roster in a later section ($2,000 biweekly → monthly).
  await advanceTo(page, "household.members");
  await expect(panel(page)).toContainText("$4,333.33 a month before deductions, for you");
  await expect(page.getByText("$1,000/month").last()).toBeVisible();
  await panel(page).getByRole("button", { name: "Use this answer" }).click();
  await expect(page.getByText("$4,333.33/month")).toBeVisible();
});

test("tax: documents that disagree are both shown, and a year mismatch is flagged", async ({ page }) => {
  await startAt(page, "tax_information");
  await page.getByRole("button", { name: "Continue" }).click();
  const entry = page.locator('[data-field-id="tax.entry_method"]');
  await expect(page.getByText("Add documents (optional)")).toHaveCount(0);
  await entry.getByRole("button", { name: "Use my documents" }).click();
  await expect(page.getByText("Add documents (optional)")).toBeVisible();
  await upload(page, file("return-2024.pdf", "RETURN2024 Form 1040"), file("return-2025.pdf", "RETURN2025 Form 1040"));
  await expect(page.getByText(/suggested answers? to review/)).toHaveCount(2);

  await advanceTo(page, "tax.year");
  await page.locator('[data-field-id="tax.year"] input').fill("2025");
  await advanceTo(page, "tax.adjusted_gross_income");
  await expect(panel(page)).toContainText("Your documents disagree");
  await expect(panel(page)).toContainText("$52,000");
  await expect(panel(page)).toContainText("$61,000");
  await expect(panel(page).getByText("This is from 2024, not the tax year you chose.")).toHaveCount(1);
  await panel(page).getByRole("button", { name: "Use this answer" }).last().click();
  await expect(page.locator('[data-field-id="tax.adjusted_gross_income"] input')).toHaveValue("61000");
});

test("skipping tax savings moves straight on and keeps household answers", async ({ page }) => {
  await startAt(page, "tax_information");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.locator('[data-field-id="tax.entry_method"]').getByRole("button", { name: "Skip tax savings for now" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Current Coverage and Benefits")).toBeVisible();
  const draft = await page.evaluate(() => JSON.parse(localStorage.getItem("ilera_intake_draft") ?? "{}"));
  expect(draft.answers["household.members"]).toHaveLength(2);
  expect(Object.keys(draft.answers).filter(k => k.startsWith("tax.") && k !== "tax.entry_method")).toEqual([]);
});

test("unreadable files and untrusted model output are handled at the boundary", async ({ page, request }) => {
  await startAt(page, "household_assets");
  await upload(page,
    file("scan.pdf", ""),
    { name: "photo.gif", mimeType: "image/gif", buffer: Buffer.from("GIF89a fake") },
    file("odd.pdf", "HOSTILE statement"));
  await expect(page.getByText("This looks like a scanned PDF. Try a clear photo of the page instead.")).toBeVisible();
  await expect(page.getByText("Use a PDF, JPG or PNG file.")).toBeVisible();
  // Of four model suggestions only the valid income survives; the SSN is scrubbed from its evidence.
  await expect(page.getByText("1 suggested answer to review in the questions ahead")).toBeVisible();
  await advanceTo(page, "household.members");
  await expect(panel(page)).toContainText("$3,000 a month before deductions, for you");
  await expect(panel(page)).toContainText("Gross pay for SSN [redacted]");
  await expect(panel(page)).not.toContainText("123-45-6789");

  // Only readable documents reached the model, each without storage or tools, schema-constrained.
  const sent = await (await request.get("http://127.0.0.1:4517/__requests")).json();
  expect(sent.length).toBeGreaterThanOrEqual(1);
  for (const r of sent) expect(r).toMatchObject({ path: "/openai/v1/chat/completions", store: false, model: "e2e-documents", strict: true });
  expect(sent.every((r: { tools?: unknown }) => r.tools === undefined)).toBe(true);
});
