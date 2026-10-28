# Current intake completeness audit — October 12, 2026

## Finding

The current questionnaire has material screening gaps. It has not been verified as sufficient for all program pathways. The UI/answer refactor improved reliability; it did not establish complete policy coverage. Some cases can support a preliminary conclusion, while other cases must remain unresolved pending focused follow-ups. This audit is not an agency decision.

## Execution and evidence limits

Six fresh direct research invocations used Ilera's configured Azure model, specialist program registry and program-scoped RAG. Each received the current SCREENS catalog, including visibility conditions. These were research-only calls, not the hosted Durable assessment endpoint and not real cases. Each specialist performed one retrieval query returning eight passages. All six returned, and all six received a correction pass. Exact prompts, retrieved passages, initial outputs and corrected outputs are adjacent files.

Initial results often cited document identifiers rather than full retrieved passage identifiers. Correction passes resolved these reference issues for Medi-Cal, PFL, VA and Medicare; IHSS and tax still have unmatched identifiers. Reference matching alone does not establish that a passage supports a claim. Several outputs drift into other programs, ask for application identifiers and completed certification during screening, or label already-collected/derived facts as missing. Treat raw outputs as research leads, not approved requirements. Limited retrieval does not prove an exhaustive inventory.

## Reviewed implementation gaps

| Area | Current coverage | Follow-up needed when relevant | Possible lookup aid |
| --- | --- | --- | --- |
| Eligibility unit | Resident headcount and recipient marital status | Member ages/relationships; spouse/dependent/tax-filing relationships; whose income is being reported. Compute each program's unit from inputs. Names of other members are unnecessary for this calculation. | Tax return if filing/dependency relationships are unknown |
| Income | One monthly household bucket, retained without invented midpoint | Income source, owner, gross amount and period; spouse income where relevant. Refine precision when the reported range cannot resolve a rule or straddles its threshold. | Paystub, Social Security/benefit award, pension statement |
| Assets | Types selected | Values, ownership and applicable exclusions on asset-tested pathways; dates/details only for relevant transfers or complex ownership. Do not ask user to calculate countable assets. | Balance statement; property/trust records when relevant |
| PFL caregiving | Relationship, work impact, optional leave date, CASDI question, clinician availability | Base-period qualifying wages; work/job-seeking status at leave onset; prior PFL usage and relevant overlapping payments; claim start/wage-loss dates. Clarify SDI vs voluntary plan where appropriate. Existing relationship can be evaluated without duplicating the question. | Paystubs/earnings history, previous EDD benefit record |
| Medicare | Age, broad health coverage, broad disability/benefit signals | Active A/B parts and effective dates where relevant; disability-benefit start timing, ALS/ESRD details, and applicable insured/residency facts for new eligibility routes. MSP financial details require California-specific policy. | Medicare card, SSA award, existing clinician diagnosis record if unknown |
| VA PCAFC | Military connection, VA contact, coverage, rating bucket, medical discharge question, six-month care need, caregiver age, relationship/coresidence | Confirm current VA health enrollment if broad answers do not establish it. For a nonfamily caregiver not living together, willingness to live full-time with veteran. Verify rating buckets resolve the 70% boundary. Clinical depth may still require targeted follow-up; VA assessment stays downstream. | VA enrollment/rating record if unknown |
| VA pension/Aid and Attendance | Broad service/pension signals, household income bucket, asset types, ADLs | Separate pathway from PCAFC. Service dates/character, veteran/spouse income and assets, medical-expense amounts and relevant transfer facts need a distinct rule-backed branch. Exact branch authoring not completed. | DD214, benefits/financial statements, expense records |
| Tax | Broad support, residence, paid-care and expense flags | Tax year, relevant filing/dependency tests, earned-income/work facts for taxpayer/spouse, qualifying-person incapacity, expense amounts/reimbursements and relevant provider relationship. Different dependency/credit/deduction tests require separate rules. | Tax return, invoices and reimbursement records |
| IHSS | CA address, residence, Medi-Cal status, care needs and clinician availability | Resolve pending/uncertain Medi-Cal and underlying financial pathway where needed; clarify actual personal-care/supervision/paramedical need. Completed SOC 873/SOC 321 and provider enrollment checks belong to application/authorization, not a universal prerequisite for preliminary fit. | Existing benefit/assessment record or existing clinical note if facts unknown |

These are reviewed gaps and research leads, not a certified complete rule inventory. In particular, SSI/SSDI, regional-center and ABLE-related intake signals have no dedicated specialist in the six-agent registry; cross-program mentions do not substitute for dedicated policy coverage.

## Official current cross-checks

- DHCS MAGI method uses tax-filing and countable-income rules: https://www.dhcs.ca.gov/medi-cal/help/
- DHCS current asset FAQ confirms asset testing on applicable pathways starting January 2026, exclusions, household-count caveat, and transfer date relevance: https://www.dhcs.ca.gov/medi-cal/help/asset-limit-frequently-asked-questions/
- EDD PFL requirements distinguish lost wages, work/job-seeking at leave onset, qualifying base-period earnings, medical certification and filing timing: https://edd.ca.gov/en/disability/Am_I_Eligible_for_PFL_Benefits
- Medicare disability/ALS/ESRD routes and benefit timing: https://www.medicare.gov/basics/get-started-with-medicare/other-paths
- VA PCAFC criteria distinguish enrollment, rating, discharge, care duration and family/coresidence requirements; designation/training/home assessment follow application: https://www.va.gov/family-and-caregiver-benefits/health-and-disability/comprehensive-assistance-for-family-caregivers/
- IRS qualifying-person/work-related expense rules: https://www.irs.gov/publications/p503

## Intake vs tasks

Ask brief conditional questions within their topics. Known self-reported facts do not automatically create document tasks. An unsure response should create a relevant unresolved fact only where a viable pathway needs it; offer specific lookup instructions and record what fact the lookup resolves. Creating/signing certifications, collecting form identifiers and completing agency/provider processes remain downstream. A range or missing input must keep the affected criterion unresolved rather than imply eligibility or ineligibility.

No intake questions or production policy were changed during this research session. A follow-up implementation should create a criterion-to-field matrix with supported jurisdiction/effective dates, computed units, visibility triggers and unresolved states before asserting completeness.
