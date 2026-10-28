Resolution guidance content
===========================

The generated authoring schema is `docs/resolution-template.schema.json`.
Add one JSON file per canonical fact. `load_templates()` validates every file and
publishes only `status: "reviewed"` templates. Draft resources never reach tasks.
Only one reviewed template may target each fact. The current scope is the existing
California pilot; jurisdiction-specific selection must be added before expanding it.

A template supplies presentation and retrieval help. It does not change eligibility
rules, introduce new facts, or make documentation mandatory for self-report screening.
Until reviewed content exists, tasks have manual entry and no invented links.

Authoring shape (illustrative placeholders; replace before marking reviewed):

```json
{
  "template_id": "recipient-medicaid-status",
  "category": "coverage",
  "profile_path": "care_recipient.medicaid_status",
  "status": "draft",
  "title": "Confirm Medi-Cal enrollment status",
  "description": "RESEARCH: explain why this information matters.",
  "guided_steps": ["RESEARCH: where to find the information.", "RESEARCH: which information to report."],
  "acceptable_evidence_types": [],
  "methods": [{"kind": "manual_entry", "label": "Enter information"}],
  "resources": []
}
```

Each researched resource has:

- `resource_id`, `kind` (`portal`, `form`, `document`, `contact`, `instructions`), `title`.
- `url`, `phone`, and/or `instructions` as the actual destination or walkthrough.
- `source_url` for attribution and `checked_on` as an ISO date.

`input_schema` on a task is generated from the canonical fact type, never authored by
a template. `targeted_question` is also supported for direct answers. Document upload
is reserved in the model but rejected until a document ingestion, extraction, and
user-confirmation adapter exists; do not publish a method that the API cannot complete.

Research may reveal a missing canonical field, a constrained answer vocabulary, or
several independently required facts. Add that typed field and intake binding, and
update the reviewed policy first. Do not cram a new concept into an unrelated existing
field or put application/agency work into screening-resolution templates.

Categories are `financial`, `coverage`, `medical`, `household`, `employment`, and
`general`. Category describes the information being resolved, not the program:
Medi-Cal enrollment is `coverage`, while an income amount is `financial` even when
both support Medi-Cal. It is copied onto the task for home-screen grouping and
filtering and does not select rules or impose evidence requirements. Templates
without a category, and tasks without reviewed templates, default to `general`.
Templates retain a stable `template_id` but do not have a version field.
