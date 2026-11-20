# Intake uploads: recommended first release

**November 15, 2026 — refreshed research.** All six hosted specialists returned; their answers were 67–89 words each. Current agency pages were checked separately because every cited corpus passage has an unverified effective date.

**Decision: offer optional document assistance through one shared collection, with entry points in Work, Household, Tax and Coverage.** Keep manual entry available. Documents should suggest facts for review, rather than determine eligibility.

| Priority | Optional record | Useful intake facts | Boundary |
| --- | --- | --- | --- |
| 1 | Recent paystub or current SSA/pension letter | Income components in `household.members`; `caregiver.sdi_deductions` from CASDI | Confirm person, gross amount and period. One record cannot establish complete household income or PFL eligibility. [EDD](https://edd.ca.gov/en/disability/Am_I_Eligible_for_PFL_Benefits), [SSA](https://www.ssa.gov/manage-benefits/get-benefit-letter). |
| 1 | Current Medi-Cal/IHSS notice | `recipient.medicaid_covered`; relevant `recipient.program_statuses` entry | Confirm current status. Approval and actually receiving services are different. [DHCS notices](https://www.dhcs.ca.gov/medi-cal/use/). |
| 1 | Medicare card or coverage record | `recipient.medicare_parts`, `recipient.medicare_part_a_start`, `recipient.medicare_part_b_start` | Read parts/dates; exclude the Medicare number and confirm coverage remains active. [Medicare](https://www.medicare.gov/basics/get-started-with-medicare/using-medicare/your-medicare-card). |
| 1, VA branch | Short VA benefit/service summary | `recipient.va_rating`; pension type when explicitly stated | Rating, pension receipt and health enrollment are separate facts. [VA letters](https://www.va.gov/records/download-va-letters/). |
| 2, tax review | Selected filed 1040 pages; W-2; existing 2441 when relevant | `tax.adjusted_gross_income`, historical filing status and dependent-care benefits | Match `tax.year`. Box 10 has no dedicated intake amount field; do not copy it into recipient-specific reimbursements or current employer availability. [1040](https://www.irs.gov/pub/irs-prior/f1040--2025.pdf), [IRS dependent-care guidance](https://www.irs.gov/publications/p503). |
| 2, when unsure | Employer plan guide plus personal enrollment/claims confirmation | `tax.dependent_care_fsa_available`; reimbursement components after allocation | Guide = offer; enrollment = election; paid claim = reimbursement. User confirms which applies. |

**Defer** routine bank/investment aggregation, expense piles, full tax returns, clinical files and immigration/identity papers. Do not require a new signed SOC 873 to finish screening; certification belongs to service authorization. [CDSS IHSS](https://www.cdss.ca.gov/in-home-supportive-services).

**Tax entry:** Upload documents / Enter manually / Skip tax savings for now. Skipping must preserve household members, current income, spouse/dependency relationships and assets. Keep filed-return review separate from planning another year.

**Review rule:** show the source page, person, date/year and proposed answer; require confirmation. Missing, conflicting or stale information remains unresolved. Reuse evidence across sections only when the person, period and meaning match.

**Expected reach:** earlier explicit scenarios supported candidates for 5/48, 11/93 and 3/54 visible questions, plus partial roster help. The unchanged 145-field schema does not support claiming uploads fill most intake questions.

**Next decision:** prototype priorities 1–2 with synthetic documents, measure extraction accuracy and time saved, then finalize collection/retention rules for the dedicated document-processing Azure resource. No upload functionality was implemented by this research.

[Detailed field matrix and exclusions](../document-uploads-2026-10-28/document-to-field-matrix.md) · [Scenario assumptions](../document-uploads-2026-10-28/coverage-scenarios.json) · [Fresh specialist evidence and review](research-notes.md)
