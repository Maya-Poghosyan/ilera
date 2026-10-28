Eligibility resolution backend
==============================

This flow resolves missing user-answerable facts after initial intake. It does not
plan applications or ask a caregiver to obtain an agency approval to finish screening.

Implemented flow:

```
CaseProfile + ProgramPolicy -> ProgramEvaluation.required_fact_paths
                           -> shared ResolutionTask per canonical fact
                           -> typed result -> profile update -> re-evaluate -> reconcile
```

Models live in `backend/app/eligibility/resolution_models.py`; planning and completion
live in `resolution.py`. The case's `resolution` bundle persists task history,
deferrals and idempotency receipts together with its facts, using existing case JSON
storage. Resolution mutations use a case-row transaction in Postgres or a process lock
in the development in-memory store. There is no separate parallel fact/task store.

API contract
------------

All endpoints use existing case access authorization. Owned cases require the owner;
unowned cases follow the existing anonymous-intake access contract.

- `GET /api/eligibility-resolution/{case_id}`: current projection, without a write.
- `POST /api/eligibility-resolution/{case_id}/refresh`: persist the reconciled projection.
- `POST /api/eligibility-resolution/{case_id}/tasks/{task_id}/result`: supply a result.
- `POST /api/eligibility-resolution/{case_id}/tasks/{task_id}/defer`: save for later.

GET accepts optional `program_id`; shared tasks appear under both primary and related
programs. Responses include `fact_revision`, `task_revision`, `evaluations`, `tasks`,
and `policy_coverage`. Coverage reports which policies were evaluated; it is not a
claim that every program or its policy has been reviewed for production.

Example completion (use revisions from the latest response):

```json
{
  "idempotency_key": "a-client-generated-unique-key",
  "expected_fact_revision": 3,
  "expected_task_revision": 2,
  "method": "manual_entry",
  "value": "Enrolled now"
}
```

Value is typed by the task's `input_schema`. Empty/missing values cannot count as
known evidence; explicit false, zero and empty lists can be legitimate answers.
A result may establish ineligibility: resolving uncertainty is distinct from qualifying.
Submitting a result updates the fact through `write_fact`, evaluates current policies,
and derives task resolution from remaining requirements. Invalid results roll back;
stale revisions or reused keys with different results return 409. Exact retries return
the current projection without replaying writes. Receipts retain a request digest,
not another copy of submitted values. Re-evaluation currently runs synchronously for
all loaded policies; selective scheduling/outbox work is not implemented.

Deferral body: `{"expected_task_revision": 2}`. Deferral never changes eligibility
facts, and the task remains visible. A later result may complete a deferred task.

Task/card data
--------------

A task contains canonical `profile_path`, stable case/fact-based `id`, program and
criterion links, category, uncertainty reasons, title/description, `guided_steps`, structured
`resources`, acceptable evidence types, available methods, and generated input schema.
It has `available`, `deferred`, `resolved`, or `superseded` state. Repeated planning keeps
the same ID and user state. Corrected/conflicting evidence can reopen a resolved task
with an explanation; prior completion timestamp and receipt remain available. Obsolete
unresolved obligations are superseded rather than presented as successful resolution.

Only unknown user-fact criteria on needed viable pathways generate tasks. Eliminated
routes, satisfied alternate routes, agency decisions and model/service-review errors
do not generate fabricated collection work. No deadlines or urgency levels are guessed.
Available tasks sort before deferred/history, then by shared-program impact and stable ID.

Guidance content
----------------

See `backend/data/resolution_templates/README.md`. Resources support official links,
forms, portals, contact details and instructions with source attribution/date checked.
Only reviewed templates are used. Templates have stable IDs without version fields.
Categories (`financial`, `coverage`, `medical`, `household`, `employment`, `general`)
are copied to tasks for presentation; they do not affect eligibility rules. No researched benefit guidance is bundled yet.
Manual entry and targeted answers work; upload/extraction is future work.

Remaining integration
---------------------

The frontend home screen is not wired to this API. The new evaluation is separate from
legacy Durable/MatchLevel presentation; only the bundled IHSS draft exists today.
The evaluator leaves assisted judgments unknown and external decisions pending. Intake
provenance covers the initial policy fields, not the full fact registry. Reviewed policy
sources, strict domain value vocabularies, document adapters, jurisdiction-aware templates,
and migration of legacy screens remain necessary. All case writes must eventually use
revision-aware transactions; older read/modify/save flows can still overwrite concurrent
resolution updates. Do not claim end-to-end concurrency protection across those flows.
