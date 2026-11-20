# Research execution and evidence register

Date checked: October 28, 2026 (America/Chicago). This folder contains research-only artifacts. No user documents were requested, no real document was processed, no application/infra file was edited, no Azure resource was provisioned, and no deployment or eligibility case was created. The only model-backed operation attempted was the explicitly requested research-specialist consultation using existing resources.

## Local evidence inspected

- `backend/app/intake/schema.py`, `logic.py`, `household.py`, `mapping.py`: live working catalog, validation/cleanup, context and profile projection.
- `frontend/src/lib/intake-schema.ts`, `intake-flow.ts`, `household-data.ts` interface/import context; `frontend/src/app/intake/page.tsx`, `components/intake/question-field.tsx`: frontend conditions/pages, draft/review, intro documents and tax-year guidance. No UI was changed or live deployment equivalence claimed.
- `backend/app/forms/profile_paths.py`, `backend/app/eligibility/facts.py`, `backend/tests/intake_helpers.py`: form/profile contract, fact provenance and synthetic fixture patterns.
- `docs/intake-flow.md`, `intake-immigration-followups.md`, `policy-research.md`, `policy-retrieval-scoping.md` references, `eligibility-resolution-api.md`, `reference-guide-storage.md`, `vnet-migration-status.md` network references, and email architecture references discovered by search.
- October 12 intake completeness `review.md` and all six `*-document-question-research.json`; October 14 medical-expense `findings.md`.

The exact catalog was saved before analysis; source SHA-256 fingerprints are in `inspected-source-hashes.json`. Other work was already modified in this checkout. This task's new files are confined to this folder; an unchanged tracked-path status list was verified at completion. Fingerprints describe the local working sources, not a production-deployment attestation.

The earlier JSON outputs were read as **unverified research leads**. Examples of unsuitable carryover: suggestions for claim/Medicare identifiers, old `recipient.monthly_income_range`/`recipient.has_certifying_clinician` references, a generic stopped-work/reduced-hours PFL trigger, and treating a policy manual itself as a user financial document. These do not describe today's catalog or establish current requirements. Prior review already reported citation and scope concerns. Current agency sources were checked independently where this report makes policy claims.

## Hosted specialist consultation

The existing CLI in `backend/app/agents/research.py` was inspected. It uses six program scopes (`ihss`, `medical`, `pfl`, `va`, `medicare`, `tax`), existing hosted Postgres retrieval and the configured research model. This was a consultation through Ilera's specialist research interface, not delegated agent work or new resources.

Exact request:

```text
For your program, which existing household documents materially support preliminary caregiver screening versus agency application verification? Address owner, date, income versus assets, benefits offered versus received, and unsupported inferences. Cite supplied evidence and flag unverified historical sources.
```

Invocation from `backend`:

```sh
.venv/bin/python -m app.agents.research --program all --as-of 2026-10-28 --k 3 \
  'For your program, which existing household documents materially support preliminary caregiver screening versus agency application verification? Address owner, date, income versus assets, benefits offered versus received, and unsupported inferences. Cite supplied evidence and flag unverified historical sources.' \
  --output ../docs/research/document-uploads-2026-10-28/hosted-specialists.json
```

1. Sandbox attempt: database DNS resolution failed; eventual `Research failed (PoolTimeout)`; exit 1.
2. Retry with user-approved network escalation: `Research failed (PoolTimeout)`; exit 1.

Neither produced `hosted-specialists.json` or any fresh specialist answer/passages. No successful model response, policy coverage, or current corpus evidence is claimed. No secrets/config values were printed by this report. Existing private-network notes suggest a connectivity constraint, but the failed retry does not diagnose its exact cause. Public database access was not enabled, and no VPN/tunnel was provisioned. Further hosted consultation requires a working authorized connection.

## Source status and selection

Official agencies and form instructions are the basis for policy statements. Primary product documentation supports product workflow descriptions only. Search snippets were leads; central tax forms, DHCS FAQ, EDD eligibility, Medicare card, SSA letters, VA criteria and Microsoft handling/API pages were opened. The report's inline citations specify relevant sections/pages. `source-register.json` lists URLs cited in the report/matrix; it is a navigation register, not a full policy corpus or claim that every linked supporting form page was read exhaustively.

Important version boundaries:

| Evidence | What was verified | Limit |
| --- | --- | --- |
| IRS 2025 1040, Schedule A and 2441 PDFs; current 2025 instructions/publications | Actual printed fields, year, line/page semantics | 2025 return review only; not final 2026 instructions. |
| IRS 2026 W-2 instructions and Pub. 15-B | Box 10 meaning and inconsistent exclusion references | W-2 passage fetched says $5,000; Pub. 15-B says $7,500 / $3,750. No calculation made; resolve year-specific law/guidance before calculating. |
| Current DHCS asset FAQ | Dated current/future schedules, exclusions and transfer guidance | Not exhaustive county/waiver/MSP rule validation; do not substitute resident headcount for program unit. |
| EDD, DOL and CRD | PFL wage/SDI and separate leave-notice/job-protection evidence | No employer decision or complete leave-law engine was evaluated. |
| SSA/Medicare/VA current pages | Retrieval paths and facts stated by letters/cards, distinct program conditions | Individual record content varies; there is no guarantee every letter supplies every mapped field. |
| Microsoft/OpenAI official docs | Architectural modalities, model/schema possibilities and service handling statements | No actual document resource configuration, model compatibility, region, contract or monitoring approval was verified. OpenAI public API docs alone do not establish Azure behavior. |
| BenefitsCal/CalSAWS guide | Primary historical guide's shared document-center workflow | URL path is 2021; no current live UI or extraction behavior test. |
| TurboTax and GetYourRefund | Current primary help descriptions of import and interview/review | No extraction benchmark, conversion improvement or Ilera suitability guarantee. |

One guessed TurboTax W-2 deep link failed; the cited general TurboTax import page opened successfully. An older Microsoft Document Intelligence privacy URL failed; its current Foundry privacy page opened successfully and is cited. Official source pages may change; revisit before production policy decisions.

## Offline quantification and validation

Run from repository root:

```sh
backend/.venv/bin/python docs/research/document-uploads-2026-10-28/coverage-analysis.py
```

This script imports intake logic, constructs synthetic answers, completes permissible unsure/default answers, cleans/validates them, and evaluates actual visibility rules. It calls no hosted services. Document coverage is an explicit **hand-authored hypothesis set** intersected with visible fields, not inferred from model extractions. Scenario JSON saves its full denominator and candidate list. Subquestions, number of documents and caregiver effort are not the counting unit. In particular, partial roster/coverage help is excluded from the numerator, and identity-copying is not counted as an upload benefit.

Validated: 145 unique catalog question IDs; 28 matrix IDs in each of the three linked tables; all contract/scenario JSON parses; scenario counts recompute; exact fully spelled question IDs in the report/matrix match the catalog or are explicitly labeled derived/roster values. The extraction contract is illustrative, not an executable JSON Schema or a production API. No app tests or deployment were appropriate because only research artifacts were changed.

## Next research needed

- Retry six-program hosted retrieval once authorized connectivity works; evaluate every cited passage's jurisdiction/date, not just retrieval success.
- Resolve 2026 tax-rule/form-edition discrepancy, CA conformity and missing tax-purpose/reference-period fields before savings estimates.
- Define program-specific gross/countable income, ownership and eligibility units before financial aggregation.
- Validate exact VA survivor versus Veteran subjects, multiple service episodes and next-12-month forecasting.
- Review CFRA statewide employer-size inputs, federal employee pathways and local notice variants.
- Measure extraction on public templates and representative synthetic/redacted samples, then review actual UX burden; no real user documents needed for this research stage.
- Verify dedicated Azure document resource deployment/API compatibility, monitoring/retention, application authorization, deletion and contract coverage before making user-facing handling promises.
