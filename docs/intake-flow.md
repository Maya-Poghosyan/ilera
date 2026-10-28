# Intake flow — October 14, 2026

The catalog in `backend/app/intake/schema.py` defines five sections: About You;
Who are you caring for?; Care Needs; Work and Financials; Current Coverage and
Benefits. Each begins with an introduction page. Explicit `page_group` values
keep related controls together. Conditional follow-ups use `show_when`, evaluated
in browser and server. Only the final roadblocks question is optional.

Support goals begin Care Needs. Basic current coverage and Medicare/immigration
follow-ups belong to Current Coverage and Benefits. Caregiver paid-work follow-ups
belong to Work and Financials; tax-residency follow-ups follow the tax-year page.
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

The financial introduction suggests pay statements, employer benefits, benefit
letters, account statements and tax returns. Reduced hours or stopped work alone do not activate leave questions. Only explicit
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

Save progress explicitly stores a browser draft; reload offers resume. New
answers are not autosaved. Start over clears immediately. Left/right arrows navigate using the same validation as the buttons, except while
editing text, dates, selects or other interactive controls. Right arrow never submits
the final page. Stable page anchors accommodate branches. Resume computes the last
completed question page from the current visible flow, including migrated drafts;
partially filled later pages do not become the resume point. Submission validates every visible required question.

## Verification

Run `npm run test:intake`, `npx tsc --noEmit`, and ESLint in `frontend`.
Frontend contract checks load the real backend schema. Browser walkthroughs cover
actual controls and navigation. In-memory HTTP checks cover complete validation
and profile projection, replacing only the external eligibility starter so
synthetic cases are not sent to Azure. No new backend unit tests were added for
this restructure. Backend/frontend must ship together; no deployment was requested.

Support goals use seven plain-language choices. Saved legacy choices are translated
and deduplicated. VA follow-ups use military/coverage evidence; merging general care
goals does not activate VA questions for everyone.

Only the five section introductions render page titles. Question pages render
their question labels without extra serif headings. Tax year precedes the recipient
filing questions. Joint-return status is derived from recipient.tax_filing_status,
not collected twice; uncertain filing plans remain unresolved.

Recipient citizenship/immigration category and its conditional status-detail question
now follow the recipient identity page in Who are you caring for? They depend only
on explicit citizenship No and the chosen status, not answers in later sections.
Program-specific residence-history questions remain in coverage; tax residency
remains in financials. Neither is a repeat of the basic immigration category.
