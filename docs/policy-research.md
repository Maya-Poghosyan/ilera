# Ad hoc policy research

Run from `backend` using its virtual environment and existing `.env`. This command
uses the same Azure/OpenAI deployment and hosted Postgres pgvector corpus as the
eligibility specialists, with a separate research prompt and cited evidence.
It does not create cases or run eligibility gates. It reads the existing index;
it never ingests or rebuilds policy documents. Database/model credentials are
loaded through the existing Settings class, not passed in shell arguments.

```sh
cd backend

# One specialist, one question, five passages, one model call
.venv/bin/python -m app.agents.research --program medical \
  'How does citizenship or immigration status affect California Medi-Cal eligibility for the care recipient?'

# Compare all six specialists; at most three run concurrently
.venv/bin/python -m app.agents.research --program all \
  'For your program, whose citizenship matters: caregiver, care recipient, both, or neither? Cite the rule and distinguish citizenship from immigration status.' \
  --output /private/tmp/ilera-citizenship-research.json

# Focus retrieval when the question combines several issues
.venv/bin/python -m app.agents.research --program ihss medical \
  'Which immigration facts should our intake ask for each person?' \
  --query 'recipient citizenship immigration status eligibility' \
  --query 'caregiver provider work authorization enrollment' --k 5

# Cheapest option: retrieval alone, no answer model
.venv/bin/python -m app.agents.research --program pfl --retrieve-only \
  'citizenship immigration status eligibility'

# Longer research requests can live in files
.venv/bin/python -m app.agents.research --program tax \
  --question-file /private/tmp/tax-question.txt \
  --output /private/tmp/tax-answer.json
```

Program keys: `ihss`, `medical`, `pfl`, `va`, `medicare`, `tax`, or `all`.
Select only relevant programs for lower cost. Repeat `--query` to retrieve distinct
aspects; overlapping passages are deduplicated before the single answer call per
program. `--k` accepts 1–20 and defaults to 5. JSON contains question, retrieval
queries, backend, model, and each specialist's answer plus original passages,
document identifiers, pages, URLs and similarity scores.

Answers are grounded in retrieved passages, not guaranteed complete or current
policy. Inspect the evidence and rerun focused searches for gaps. Citation text
is model-generated and should be checked against the included evidence. No
automatic web lookup occurs. Missing configuration, index or connectivity fails
the command rather than silently using local documents. Without `--output`, JSON
prints to stdout. Output files may contain the supplied question: use policy
questions or anonymized scenarios rather than identifiable case details.

Jurisdiction/date scoping is now explicit:

```sh
.venv/bin/python -m app.agents.research --program medical \
  --state CA --as-of 2026-10-14 \
  'Which citizenship rules apply to the care recipient?'
```

The state defaults to CA; the date defaults to the current UTC date. Federal sources
are included within each program scope. Output includes policy authority, version,
known applicability dates, and a warning marker for unverified effective dates.
The additive hosted metadata migration must precede deployment of this version:
see [scope architecture and rollout](policy-retrieval-scoping.md).
