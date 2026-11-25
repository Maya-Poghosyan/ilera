// Local stand-in for the dedicated document Azure OpenAI deployment (OpenAI v1 chat completions).
// Replies are chosen by a marker word in the document text, so specs control what the "model" says
// and the real backend still parses, validates and scrubs it. GET /__requests shows what was sent.
import http from "node:http";

const PORT = Number(process.env.FAKE_OPENAI_PORT ?? 4517);
const src = (page = 1, evidence = "Earnings statement", as_of = null) => ({ page, evidence, as_of });
const answer = (field_id, value, person, extra = {}) => ({ kind: "answer", field_id, value, person, tax_year: null, ...src(), ...extra });

const REPLIES = {
  PAYSTUB: { document_kind: "paystub", suggestions: [
    answer("caregiver.sdi_deductions", "Yes", "caregiver", { evidence: "Deductions: CA SDI line", as_of: "2026-10-31" }),
    { kind: "member_income", person: "caregiver", amount: "2,000.00", period: "biweekly", ...src(1, "Gross pay, this period", "2026-10-31") },
  ] },
  RETURN2024: { document_kind: "tax_return", suggestions: [
    answer("tax.adjusted_gross_income", "52000", "caregiver", { tax_year: 2024, evidence: "Form 1040 line 11", as_of: "2024" }),
    answer("tax.filing_status", "Single", "caregiver", { tax_year: 2024, evidence: "Filing status box", as_of: "2024" }),
  ] },
  RETURN2025: { document_kind: "tax_return", suggestions: [
    answer("tax.adjusted_gross_income", "61000", "caregiver", { tax_year: 2025, evidence: "Form 1040 line 11", as_of: "2025" }),
  ] },
  W2: { document_kind: "w2", suggestions: [
    answer("caregiver.sdi_deductions", "Yes", "caregiver", { evidence: "W-2 box 14: CASDI", as_of: "2025" }),
    answer("tax.care_reimbursements", "1200", "caregiver", { tax_year: 2025, evidence: "W-2 box 10", as_of: "2025" }),
  ] },
  DD214: { document_kind: "dd214", suggestions: [
    answer("recipient.military_status", "Veteran", "recipient", { evidence: "Block 23: release from active duty" }),
    answer("recipient.va_service_start", "1968-03-04", "recipient", { evidence: "Block 12a" }),
    answer("recipient.va_service_end", "1971-03-03", "recipient", { evidence: "Block 12b" }),
    answer("recipient.va_discharge_character", "Honorable", "recipient", { evidence: "Block 24" }),
  ] },
  // Email extraction (the email worker's care_events schema).
  IHSSVISIT: { events: [{
    title: "IHSS reassessment visit", date: "2026-12-08", date_status: "known", time: "10:00",
    timezone: "America/Los_Angeles", kind: "Appointment", action_required: "Be home for the visit",
    confidence: 0.9, explanation: "A county IHSS notice schedules a reassessment visit." }] },
  // Model output the backend must not trust: wrong person, invalid option, identifier in evidence.
  HOSTILE: { document_kind: "paystub", suggestions: [
    answer("caregiver.sdi_deductions", "Yes", "spouse"),
    answer("tax.dependent_care_fsa_available", "Definitely", "caregiver"),
    { kind: "member_income", person: "caregiver", amount: "3000", period: "monthly", ...src(1, "Gross pay for SSN 123-45-6789") },
    answer("tax.year", "2024", "caregiver", { page: 9 }),
  ] },
};

const requests = [];
http.createServer((req, res) => {
  if (req.method === "GET" && req.url === "/__requests") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify(requests));
  }
  let body = "";
  req.on("data", c => { body += c; });
  req.on("end", () => {
    const request = JSON.parse(body || "{}");
    const text = JSON.stringify(request.messages?.[1]?.content ?? "");
    requests.push({ path: req.url, store: request.store, tools: request.tools, model: request.model, strict: request.response_format?.json_schema?.strict });
    const marker = Object.keys(REPLIES).find(k => text.includes(k));
    const empty = request.response_format?.json_schema?.name === "care_events"
      ? { events: [] } : { document_kind: "other", suggestions: [] };
    const content = JSON.stringify(marker ? REPLIES[marker] : empty);
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ id: "e2e", object: "chat.completion", created: 0, model: request.model,
      choices: [{ index: 0, finish_reason: "stop", message: { role: "assistant", content, refusal: null } }] }));
  });
}).listen(PORT, "127.0.0.1");
