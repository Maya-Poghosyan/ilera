# Error handling at each Durable step

## Decision rule: raise vs return

| Situation | What the activity does | What Durable does |
|---|---|---|
| Transient failure (network, rate limit, DB connection) | `raise RetryableError(...)` | Retries per `RetryOptions`; records attempt count in execution history |
| Logic failure (bad JSON, unknown key, validation) | Catch internally → return result with `error_record` set | No retry; orchestrator reads the error record from the result |
| Both LLM and heuristic failed | Catch internally → return `match_level="assessment_failed"` with `error_record` | Orchestrator proceeds; synthesis warns the caregiver |
| Orchestrator-level invariant violated | `raise IleraError(...)` from orchestrator | Fails the entire instance; visible in portal as failed orchestration |

---

## Step 1: Orchestrator start

Raises immediately (fails the instance) — these are invariants, not recoverable:

```python
try:
    profile = CaseProfile.model_validate_json(inp.profile_json)
except ValidationError as e:
    raise ProfileDeserializationError(
        str(e), step="orchestrator_start", case_id=inp.case_id
    )

if get_profile(inp.case_id) is None:
    raise CaseNotFoundError(
        "Case does not exist", step="orchestrator_start", case_id=inp.case_id
    )
```

---

## Step 2: Eligibility gate activity

Gate functions are pure Python — they should never raise. Wrap defensively and
return `gate_error` in the result rather than failing the activity. The orchestrator
treats `gate_error` as `skip=False` (conservative: run the specialist anyway).

```python
def eligibility_gate(context):
    payload = context.get_input()
    doc_key = payload["doc_key"]
    try:
        profile = CaseProfile.model_validate_json(payload["profile_json"])
        gate_fn = GATES.get(doc_key)
        if gate_fn is None:
            return EligibilityGateResult(doc_key=doc_key, skip=False).model_dump()
        skip, reason, fast_match_level = gate_fn(profile)
        return EligibilityGateResult(
            doc_key=doc_key, skip=skip, reason=reason, fast_match_level=fast_match_level
        ).model_dump()
    except Exception as e:
        err = GateError(str(e), step="eligibility_gate", doc_key=doc_key)
        return EligibilityGateResult(
            doc_key=doc_key,
            skip=False,  # conservative fallback
            gate_error=err.to_record(),
        ).model_dump()
```

---

## Step 3: Specialist activity

Three-layer error handling:

1. **RAG failure** → `raise RagRetrievalError` (retryable) — let Durable retry
2. **LLM failure** → catch, attempt heuristic, return result with `error_record`
3. **Heuristic failure** → catch, return `match_level="assessment_failed"` with `error_record`

```python
async def _run_specialist(doc_key, profile, peer_answers, settings):
    # Layer 1: RAG — retryable
    try:
        hits = get_index().search(f"{program} eligibility requirements", k=6, program=doc_key)
    except Exception as e:
        raise RagRetrievalError(
            str(e), step="specialist_rag", doc_key=doc_key,
            index_type=type(get_index()).__name__,
        )

    # Layer 2: LLM call — retryable network errors propagate; parse errors caught
    try:
        raw = await _call_llm(system_prompt, user_prompt, settings)
    except (APIConnectionError, RateLimitError, APITimeoutError) as e:
        raise LLMCallError(
            str(e), step="specialist_llm", doc_key=doc_key,
            model=settings.openai_model, error_type=type(e).__name__,
        )

    # Layer 3: Parse/validate — not retryable, catch and fall through to heuristic
    try:
        data = json.loads(raw)
        _validate_specialist_response(data, doc_key)
    except json.JSONDecodeError as e:
        raise LLMParseError(
            str(e), step="specialist_parse", doc_key=doc_key,
            response_preview=raw[:120],
        )
    except (KeyError, ValueError) as e:
        raise LLMSchemaError(
            str(e), step="specialist_schema", doc_key=doc_key,
        )

    return _build_result_from_data(data, doc_key, hits)


def specialist_activity(context):
    payload = context.get_input()
    inp = SpecialistInput.model_validate(payload)
    instance = _SPECIALIST_CLS[inp.doc_key]()
    profile = CaseProfile.model_validate_json(inp.profile_json)
    llm_attempted = False
    llm_error: IleraError | None = None

    # Try LLM path. RagRetrievalError and LLMCallError are retryable — they
    # propagate out of the activity so Durable can retry the whole activity.
    # LLMParseError and LLMSchemaError are not retryable — caught below.
    try:
        llm_attempted = True
        result = asyncio.run(_run_specialist(inp.doc_key, profile, inp.peer_answers, get_settings()))
        return result.model_dump()
    except (LLMParseError, LLMSchemaError) as e:
        llm_error = e
        # Fall through to heuristic

    # Heuristic fallback
    try:
        er = instance._heuristic_assess(profile)
        error_record = SpecialistErrorRecord.from_error(
            llm_error, used_heuristic=True, llm_attempted=llm_attempted
        ).to_dict()
        return SpecialistResult(
            doc_key=inp.doc_key,
            program=instance.program,
            match_level=_status_to_match(er.status),
            notes=[er.rationale] + er.roadblocks,
            citations=[c.title for c in er.citations],
            eligibility_result_json=er.model_dump_json(),
            error_record=error_record,
        ).model_dump()
    except Exception as e:
        heuristic_err = HeuristicFallbackError(
            str(e), step="specialist_heuristic", doc_key=inp.doc_key,
            llm_error=str(llm_error),
        )
        return SpecialistResult(
            doc_key=inp.doc_key,
            program=instance.program,
            match_level="assessment_failed",
            notes=[
                f"{instance.program} could not be assessed. "
                f"LLM error: {llm_error.code if llm_error else 'n/a'}. "
                f"Heuristic error: {heuristic_err.code}."
            ],
            error_record=SpecialistErrorRecord.from_error(
                heuristic_err, used_heuristic=False, llm_attempted=llm_attempted
            ).to_dict(),
        ).model_dump()
```

---

## Step 4: Peer query sub-orchestration

The orchestrator catches `TaskFailedException` from each sub-orchestration and
builds a `PeerQueryResult` with `peer_error` set rather than propagating the failure.
The asking specialist is re-run with the partial peer answers it did get.

```python
# In the main orchestrator, peer query fan-out:
peer_results: dict[str, PeerQueryResult] = {}
for target_key, peer_task in zip(target_keys, peer_tasks):
    try:
        raw = yield peer_task
        peer_results[target_key] = PeerQueryResult.model_validate(raw)
    except TaskFailedException as e:
        err = PeerActivityError(
            e.inner_exception.message,
            step="peer_query",
            doc_key=asking_key,
            target=target_key,
        )
        peer_results[target_key] = PeerQueryResult(
            answer="",
            peer_error=err.to_record(),
        )
        # Log but continue — the asking specialist runs without this peer answer.
```

For `UnknownPeerTargetError` — raise before even scheduling the sub-orchestration:

```python
target_key = _resolve_doc_key(cross_program)
if target_key is None:
    # Record the warning in the specialist's result but don't block execution.
    unresolved_peers.append(cross_program)
    continue
```

---

## Step 5: Synthesis activity

```python
def synthesis_activity(context):
    inp = SynthesisInput.model_validate(context.get_input())
    profile = CaseProfile.model_validate_json(inp.profile_json)

    # Collect specialists that fully failed — warn caregiver in the result.
    failed_programs = [
        r.program for r in inp.specialist_results if r.fully_failed
    ]

    # Persist findings first (retryable if DB is down).
    try:
        _persist_findings(inp.case_id, inp.specialist_results)
    except Exception as e:
        raise FindingsPersistenceError(
            str(e), step="synthesis_persist",
            case_id=inp.case_id,
            finding_count=len(inp.specialist_results),
        )

    # LLM synthesis (retryable via Durable RetryOptions).
    synthesis_error: IleraError | None = None
    strategy: str = ""
    try:
        raw = asyncio.run(_run_synthesis_llm(profile, inp.specialist_results, get_settings()))
        strategy = format_strategy(raw)
    except (APIConnectionError, RateLimitError, APITimeoutError) as e:
        raise SynthesisLLMError(
            str(e), step="synthesis_llm",
            model=get_settings().openai_model, error_type=type(e).__name__,
        )
    except (json.JSONDecodeError, ValueError) as e:
        synthesis_error = SynthesisParseError(str(e), step="synthesis_parse")
        # Fall through to structured fallback below.

    if not strategy:
        # Fallback: build bullets directly from match levels.
        ordered = sorted(
            inp.specialist_results,
            key=lambda r: {"very_likely": 0, "likely": 1, "medium": 2,
                           "low": 3, "none": 4, "assessment_failed": 5}.get(r.match_level, 5)
        )
        lines = [f"- Apply for {r.program}" for r in ordered if r.match_level not in ("none", "assessment_failed")]
        strategy = "\n".join(lines[:7]) or "- Review eligibility results with a benefits counselor."

    error_record = None
    if synthesis_error:
        error_record = SynthesisErrorRecord(
            code=synthesis_error.code,
            step=synthesis_error.step,
            detail=str(synthesis_error),
            used_fallback=True,
            failed_specialists=failed_programs,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ).to_dict()

    return SynthesisResult(
        strategy=strategy,
        interaction_notes=_run_interaction_analysis(profile, inp.specialist_results),
        failed_specialist_programs=failed_programs,
        error_record=error_record,
    ).model_dump()
```

---

## RetryOptions configuration (in orchestrator)

```python
SPECIALIST_RETRY = df.RetryOptions(
    first_retry_interval_in_milliseconds=5_000,
    max_number_of_attempts=3,
    # Only retryable errors propagate from activities; others are caught internally.
)

SYNTHESIS_RETRY = df.RetryOptions(
    first_retry_interval_in_milliseconds=8_000,
    max_number_of_attempts=3,
)

GATE_RETRY = df.RetryOptions(
    first_retry_interval_in_milliseconds=1_000,
    max_number_of_attempts=2,
    # Gates are pure Python; a retry here is a last resort before the gate_error path.
)
```

---

## What the Durable execution history shows per failure

| Failure | Activity status in portal | Error message format |
|---|---|---|
| pgvector down | Failed (retried N times) | `[RAG_RETRIEVAL_ERROR] step=specialist_rag \| specialist=ihss \| index_type=PgVectorIndex \| ...` |
| LLM rate limit | Failed (retried N times) | `[LLM_CALL_ERROR] step=specialist_llm \| specialist=ihss \| model=gpt-4o-mini \| error_type=RateLimitError \| ...` |
| LLM bad JSON | Completed (heuristic used) | Result has `error_record.code=LLM_PARSE_ERROR`, `used_heuristic=true` |
| Both LLM + heuristic failed | Completed (degraded) | Result has `match_level=assessment_failed`, `error_record.code=HEURISTIC_FALLBACK_ERROR` |
| Peer target failed | Sub-orchestration failed | PeerQueryResult has `peer_error.code=PEER_ACTIVITY_ERROR`; asking specialist runs without it |
| Synthesis LLM failed | Failed (retried), then fallback | SynthesisResult has `error_record.code=SYNTHESIS_PARSE_ERROR`, `used_fallback=true` |
| DB write failed | Failed (retried N times) | `[FINDINGS_PERSISTENCE_ERROR] step=synthesis_persist \| case_id=X \| finding_count=6 \| ...` |
