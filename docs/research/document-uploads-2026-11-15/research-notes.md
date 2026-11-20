# Evidence and editorial review

The deployed `ad61b49` research code ran inside the existing VNet-connected API container on November 15, 2026. Six program-scoped requests, at most three concurrent, used two focused retrieval queries each and four passages per query. No case or personal document was processed. No application code or infrastructure changed during this rerun.

[specialist-research.json](specialist-research.json) contains the prompts' field targets, retrieval queries, exact bounded answers, word counts and cited evidence excerpts (up to 1,800 characters per passage). Document/page references were validated against retrieved pairs. Reference validity does not establish claim entailment. All cited passages had `date_status=unverified`.

| Specialist | Words | How the synthesis handled its recommendation |
| --- | ---: | --- |
| IHSS | 67 | Rejected signed household statements/new SOC 873 as preliminary-intake requirements; kept optional existing notices and self-report. |
| Medi-Cal | 76 | Kept current income-letter assistance; deferred general bank-statement collection and program-specific ownership calculations. |
| PFL | 84 | Kept CASDI/pay-period lookup; did not infer qualifying base-period wages, benefit amount or prior weeks from one stub. |
| VA | 76 | Kept short existing award/summary letters; separated service, pension and enrollment; omitted new medical-report requests from intake. |
| Medicare | 89 | Kept A/B dates; preferred manual reading or identifier-masked upload over collecting the entire card indiscriminately. |
| Tax | 82 | Kept W-2 Box 10 as historical evidence; resolved missing AGI evidence through the actual 1040 rather than dropping the field. Historical $5,000/$2,500 figures were not applied to 2026. |

Current sources reopened: CDSS IHSS, DHCS asset FAQ and coverage-notice guidance, EDD PFL eligibility, Medicare card guidance, SSA verification-letter guidance, VA benefit-letter retrieval, IRS Publication 503 (2025), Publication 15-B (2026), and the 2025 Form 1040. Direct citations appear in the report. Publication 15-B distinguishes 2026 limits from the historical Publication 503 edition; this report makes no savings calculation.

The working schema still has 145 question records and exactly matches the saved October 28 catalog. Therefore the existing detailed field/condition matrix and explicit scenario denominators remain useful appendices. The entire 28-document matrix, vendor architecture discussion and comparable-product survey were not independently re-audited in this concise refresh; those retain their earlier research date.

Remaining gaps: current-date metadata/entailment review for the hosted corpus, county notice variants, complete prior-PFL usage records, recipient-specific expense allocation, historical-versus-current tax facts, and extraction/UX benchmarks. The uploaded-document processing resource's production settings were not assessed here.
