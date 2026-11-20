# Intake flow — October 14, 2026

The catalog in `backend/app/intake/schema.py` defines seven sections: About You;
Who are you caring for?; Care Needs; Work and Caregiving; Household and Assets; Tax Information; Current Coverage and
Benefits. Each begins with an introduction page. Explicit `page_group` values
keep related controls together. Conditional follow-ups use `show_when`, evaluated
in browser and server. Only the final roadblocks question is optional.

Support goals begin Care Needs. Basic current coverage and Medicare/immigration
follow-ups belong to Current Coverage and Benefits. Caregiver paid-work follow-ups
begin Work and Caregiving; tax-residency follow-ups follow the tax-year page.
All gates are encountered after their prerequisites without moving unrelated
questions into identity sections. Citizenship No activates only relevant branches;
unsure/decline remains unresolved. See
[intake immigration follow-ups](intake-immigration-followups.md) for the gates.

Names, birthdays and citizenship are grouped by person. Caregiver address and
coresidence are together; shared residence supplies recipient address context.
Separate recipient address appears only when needed. Residence states are
limited to California; work state remains independent. Relationship choices
use “They are your…”. Conditions are visible selectable chips with search/add,
including regular injections, wound care and catheter care. Care tasks are asked directly; the redundant self-care boolean question is removed.
Documentation and frequency each have a separate page. Frequency follows a care-task
answer and is hidden when “None of these” is selected. Preparing certifications belongs to application work.

## Finances and work

Work authorization comes before employment questions in Work and Caregiving.
Each of Work and Caregiving, Household and Assets, and Tax Information has a title
card and a document/location guide. Shared filing/dependency facts stay with the
household; tax-year-specific amounts and savings questions follow in Tax Information.
The recipient’s work history follows the household income roster.
Document upload and an explicit tax-section skip remain proposed features, not active controls. Reduced hours or stopped work alone do not activate leave questions. Only explicit
“Have taken leave”, “Taking leave”, or “Expect to take leave” selections activate
leave/wage details. The retired check-PFL opt-in is removed and saved answers on
that branch are cleared. The leave start date is its own page and refers to the
specific leave arrangement, not the start of caregiving.
Duplicate medical-certification questions were removed.

`household.members` includes recipient, applicable spouse, caregiver and added
household/tax-family members. The caregiver appears once when also the married
or registered partner. Records contain role, relationship, age, residence, tax
link, employment, selected income sources, gross monthly amount and variation.
Known birthdays supply ages; added people retain actual ages because program
age cutoffs differ. Repeated standalone income questions were removed.

A valid roster with known residence and resident income produces
`household.reported_income_monthly`. This reported resident total is **not** a
universal countable-income figure. Nonresident spouse/caregiver information stays
available separately. Unknown amounts do not become zero. There is no separate completeness question;
the total is explicitly for listed resident members, not an independently verified
complete household. Current no-income
answers suppress redundant annual-income questions; omitted historical income
stays unknown. Expense amounts appear only after Yes.

## Coverage and applications

Medi-Cal yes automatically selects Medicaid in combined coverage/benefits.
Acronyms are expanded; the redundant both-Medicare-and-Medicaid option is gone.
Medicare Parts A/B appear only when Medicare is selected. Their coverage dates
share a row on wider screens. Controls link to official card/coverage guidance.
Progressive VA questions and VA financial details remain conditional here.

Previously applied programs refer to caregiver benefits or care services. Each
selected program has an independent status row and next-page calendar entry.
Removing a program clears its old status/date. Roadblocks are last and do not
require a previous application.

## Data and saving

Raw answers contain current catalog fields. Context derives ages, shared address,
coverage aliases and household figures. Parent changes clear hidden descendants.
Profile projection uses `write_fact` and preserves externally resolved evidence.
Raw roster and program details remain available to specialists. Citizenship No
alone does not establish ineligibility. Caregiver DOB maps to SOC 426/426A dates.

Every response and card change automatically saves a browser draft; reload offers
resume at the saved card, including partially answered cards. Start over clears
the draft immediately. Left/right arrows navigate without requiring complete answers, except while
editing text, dates, selects or other interactive controls. Right arrow never submits
the final page. Stable page anchors accommodate branches. If the saved card no longer
exists, resume falls back to the last completed question page. Submission validates
all visible questions and shows a review page listing missing or invalid answers,
grouped by section with links to the relevant cards. Review answers is also available
from each card, so caregivers can return to the list after making corrections.

## Verification

See "Testing" in the root README: browser journeys in `frontend/e2e/` and API QA in
`backend/tests/`. Backend and frontend must ship together.

Support goals use seven plain-language choices. Saved legacy choices are translated
and deduplicated. VA follow-ups use military/coverage evidence; merging general care
goals does not activate VA questions for everyone.

Only the seven section introductions render page titles. Question pages render
their question labels without extra serif headings. Tax year precedes the recipient
filing questions. Joint-return status is derived from recipient.tax_filing_status,
not collected twice; uncertain filing plans remain unresolved.

Recipient citizenship/immigration category and its conditional status-detail question
now follow the recipient identity page in Who are you caring for? They depend only
on explicit citizenship No and the chosen status, not answers in later sections.
Program-specific residence-history questions remain in coverage; tax residency
remains in financials. Neither is a repeat of the basic immigration category.

## Document assistance (optional)

Screens with `upload_documents` in the intake schema (Work and Caregiving, Household and Assets, Tax
Information, Current Coverage and Benefits) show an "Add documents" card after the section title card;
a question's `upload_when` condition shows it again on that question's page (the tax entry choice).
Upload limits are served as `document_upload` in the schema. Documents form one shared collection.

- Backend: `app/intake/documents/` — `routes.py` (HTTP boundary, spend limit), `upload.py` (file
  validation, model input), `fields.py` (`SPECS`: the single list of suggestible fields; prompt,
  output schema and validation derive from it), `extractor.py` (model call), `models.py` (contract).
  `POST /api/intake/documents` takes one PDF/JPEG/PNG as the raw body, reads it in memory and returns
  `answer` / `member_income` suggestions. Nothing is stored or logged; `store=False`, no tools.
- Frontend: `src/components/intake/documents/` — upload card, suggestion panel, shared-collection hook,
  and the response parser.
- Requires the dedicated Azure OpenAI resource `ilera-documents-openai`
  (`infra/azure/oauth/documents.tf`): `DOCUMENT_OPENAI_ENDPOINT`, `DOCUMENT_OPENAI_DEPLOYMENT`
  (vision-capable), reached only with the API's managed identity. Never uses `OPENAI_API_KEY`;
  missing settings are a server error, not a disabled feature.
- Suggestions are applied only when the caregiver selects "Use this answer". Conflicting values are
  all shown; tax figures from a different year than `tax.year` are flagged.
- Spend limit: 300 documents per hour per API replica, shared by all users.

`tax.entry_method` opens the Tax Information section: Use my documents / Enter answers myself / Skip
tax savings for now. Skipping hides only the tax questions; the tax eligibility gate still runs.

End-to-end tests: `cd frontend && TEST_DATABASE_URL=... npm run test:e2e` starts the backend against the
test Postgres through `backend/tests/e2e_api.py` (which swaps only the document model client for the
local stand-in `e2e/fake-azure-openai.mjs`) and the Next app.
