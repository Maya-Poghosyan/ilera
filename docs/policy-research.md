# Ad hoc policy research

Run from `backend` using its virtual environment and existing `.env`. This command
uses the same Azure/OpenAI deployment and hosted Postgres pgvector corpus as the
eligibility specialists, with a separate research prompt and cited evidence.
It does not create cases or run eligibility gates. It reads the existing index;
it never ingests or rebuilds policy documents. Database/model credentials are
loaded through the existing Settings class, not passed in shell arguments.

```sh
cd backend

# One specialist, one question, five passages
.venv/bin/python -m app.agents.research \
  'How does citizenship or immigration status affect California Medi-Cal eligibility for the care recipient?' --program medical

# Compare all six specialists; at most three run concurrently
.venv/bin/python -m app.agents.research \
  'For your program, whose citizenship matters: caregiver, care recipient, both, or neither? Cite the rule and distinguish citizenship from immigration status.' \
  --program all --output /private/tmp/ilera-citizenship-research.json

# Focus retrieval when the question combines several issues
.venv/bin/python -m app.agents.research \
  'Which immigration facts should our intake ask for each person?' --program ihss medical \
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
aspects; overlapping passages are deduplicated before the answer call per
program. `--k` accepts 1–20 and defaults to 5. Saved JSON contains question, retrieval
queries, backend, model, and each specialist's answer plus original passages,
document identifiers, pages, URLs and similarity scores.

Answers are grounded in retrieved passages, not guaranteed complete or current
policy. Inspect the evidence and rerun focused searches for gaps. Citation references
are validated, but claims still need checking against the included evidence. No
automatic web lookup occurs. Missing configuration, index or connectivity fails
the command rather than silently using local documents. Without `--output`, JSON
prints to stdout. Output files may contain the supplied question: use policy
questions or anonymized scenarios rather than identifiable case details.

## Compact output contract

Research `answer` is now a validated object, not an unrestricted string:
`conclusion`, `findings` (at most 3, each with document/page citations),
`next_steps` (at most 3), and `limitations` (at most 2). Total prose is capped at
150 words. Citations must match retrieved document IDs and exact page labels;
this checks references, not whether a passage entails the claim. Invalid answers
get at most one model-validation retry, then fail explicitly.

Console output omits full retrieved passages by default. Use `--include-evidence`
to print them, or `--output` to save the full evidence archive. `--retrieve-only`
still returns passages without a model call. Existing JSON consumers must adapt
from an answer string to this object.

Eligibility generation also uses a strict typed contract: a 240-character summary,
at most 3 roadblocks, 3 next steps, 4 document items, 3 missing facts and 3 followups,
and at most 220 words total. Strategy synthesis returns at most 7 bullets/180 words;
interaction analysis at most 3 items/150 words. Public eligibility/result and
strategy-string shapes stay unchanged. Overlong outputs are rejected, not truncated.

Settings: `ELIGIBILITY_MAX_OUTPUT_TOKENS=4096`, `RESEARCH_MAX_OUTPUT_TOKENS=3072`,
`AGENT_REASONING_EFFORT=low`. Budgets include hidden reasoning as well as output;
they apply per model request, not to the entire multi-tool run. Set reasoning effort
empty for deployments that do not support it. Strict output requires compatible
model/endpoint support; no unstructured fallback is introduced for specialist or
research failures. Existing interaction heuristics remain unchanged. Lower effort
and shorter generation may reduce latency, but live quality/latency have not been
benchmarked. See [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

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

## Private-network execution

The production database has public access disabled. A changed laptop IP is not
resolved by a firewall allowlist entry; use authorized private connectivity or run
research in the existing VNet-connected container. On November 15, all six research
specialists were verified there using local compact-contract code in a separate
process: 48–94 words each, 15.72 seconds total. This did not deploy the changes.
See [live check and limits](research/agent-output-validation-2026-11-15/README.md).
