# Immigration follow-ups in the person sections

The user's five-section order is preserved. About You contains caregiver identity, an immediate status follow-up after citizenship No,
and address; Who are you caring for? contains recipient identity and conditional
address. Support goals begin Care Needs. Sensitive follow-ups stay with the topic
whose eligibility they inform, after their prerequisite answers. Current Medi-Cal,
combined coverage/benefits and Medicare follow-ups are in Current Coverage and
Benefits. IDs are preserved; the version changes so saved drafts retain applicable
answers and restart navigation against the revised order.

## About You

Citizenship No immediately opens the existing broad citizenship/immigration category
question before the address, without waiting for support goals. Unsure and prefer not
to answer remain available. No document identifiers or uploads are requested. Changing
the answer to Yes clears the hidden category.

## Work and Financials

| Question | Show when |
| --- | --- |
| Current U.S. work authorization | The same paid-care goal, with a category answer that is not declined |
| Tax residency for the requested tax year | Explicit citizenship No and a tax-benefits goal |

Paid Family Leave interest alone does not activate these questions. Work
authorization is not a PFL eligibility test and does not establish the recipient's
eligibility. Citizenship/category answers do not automatically establish work
authorization. Category options include U.S. national, permanent resident, another
status, no current status, unsure and decline. The tax question asks about tax
residency rather than assuming it from immigration status.

## Current Coverage and Benefits

| Question | Show when |
| --- | --- |
| Recipient citizenship/immigration category | Explicit citizenship No, a coverage/care-related goal or current Medicare, and age 19+ or current Medicare |
| More specific status/situation | Recipient category is Another immigration status |
| Date permanent-resident status began | Permanent resident, age 19+, relevant coverage/care goal, and Medi-Cal coverage No or unsure |
| Five years of continuous U.S. residence | Permanent resident, age 65+, checking relevant coverage, not already on Medicare, and insured work history No or unsure |
| Pregnancy or the year after pregnancy ended | The noncitizen adult new-coverage branch, with a status answer that is not declined or U.S. national |
| Foster care at the 18th birthday | The same new-coverage branch, for ages 19–25 |
| Citizen/resident category for dependent tax rules (in Work and Financials) | Explicit citizenship No and a tax-benefits goal |

The status-detail choices distinguish refugee, granted asylum, COFA citizenship,
TPS, DACA, parole, temporary visa/status, pending application, another status,
unsure and decline. Broad/other/pending categories remain unresolved when more
precision is needed; choosing a category does not establish agency eligibility.

The primary category is not requested for a child solely for Medi-Cal screening,
or solely for dependent tax screening. Dependent tax categories include U.S.
national, U.S. tax resident, Canadian resident and Mexican resident; other dependent
tests still apply. Five years of U.S. residence is not a blanket condition for
Medi-Cal or every Medicare enrollment pathway. The permanent-resident start date
and continuous-residence answer are different facts.

## Evidence, privacy, and cleanup

The two citizenship questions offer only Yes and No. Every sensitive follow-up allows
unsure/decline. An uncertain or declined citizenship answer does not trigger
status probes or become False. Declining the caregiver's category suppresses the
nested work-authorization question. Future permanent-resident start dates are
invalid. No immigration document numbers, IDs, uploads, or account numbers are
requested. Eligibility specialists receive the raw structured self-reports with
instructions to distinguish work, coverage, residence and tax rules.

Server and browser use the same schema conditions. Clearing or changing citizenship,
goals or status removes answers from hidden branches, including dependent dates.
The caregiver category remains when goals change because it now follows citizenship alone.
No new automatic immigration disqualifier is added.

## Policy references checked

- [DHCS immigration-status coverage guidance](https://www.dhcs.ca.gov/immigration-status-and-changes-to-medi-cal-eligibility/)
- [DHCS adult-expansion status matrix](https://www.dhcs.ca.gov/services/medi-cal-resources/medi-cal-eligibility-division/all-county-welfare-directors-medi-cal-eligibility-division-information-letters/eligibility-based-on-immigration-status-for-the-adult-expansion-freeze-effective-january-1-2026/)
- [CMS Medicare eligibility pathways](https://www.cms.gov/medicare/enrollment-renewal/original-part-a-b)
- [CDSS IHSS provider rules](https://www.cdss.ca.gov/inforesources/letters-regulations/legislation-and-regulations/confidentiality-regulations/div30-ch30-700-thru-sec30-785)
- [EDD PFL eligibility](https://edd.ca.gov/en/disability/Am_I_Eligible_for_PFL_Benefits/)
- [IRS tax residency](https://www.irs.gov/publications/p519) and [dependent tests](https://www.irs.gov/publications/p501)

These are question-routing rules, not a complete legal eligibility decision tree.
Historical policy changes, current coverage scope, renewals and complex statuses
may still need specialist follow-ups. Existing program-specific questions remain
in the later sections.

## October 28, 2026 review

Attempted to query all six hosted policy research specialists through
`app.agents.research`; the hosted Postgres index was unreachable (PoolTimeout),
so no new agent answers were obtained. Checked current official EDD, CDSS and IRS
sources directly instead. EDD states that citizenship/immigration status does not
affect PFL eligibility. CDSS distinguishes provider enrollment and work-eligibility
verification from initial screening. IRS distinguishes tax residency/dependent tests
from identification numbers required on a filed return.

Product decision: collect a broad self-reported category immediately as requested;
ask work authorization only for paid-caregiver interest and tax residency only for
relevant tax pathways. Broad immigration category alone does not establish either
fact. Defer document numbers, SSNs/ITINs, identity documents and uploads to agency
application/enrollment verification. This is a screening design decision, not a claim
that agencies never require those identifiers. Recipient-specific coverage/residence
questions retain their existing separate gates.

Additional official references checked:
- https://www.cdss.ca.gov/inforesources/letters-regulations/legislation-and-regulations/confidentiality-regulations/div30-ch30-700-thru-sec30-785
- https://www.irs.gov/individuals/international-taxpayers/nonresident-aliens-dependents
