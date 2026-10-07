"""Main eligibility orchestrator.

  Phase 1 — Gate fan-out (parallel): fast deterministic eligibility checks.
  Phase 2 — Specialist fan-out (parallel): LLM assessment for active programs.
  Phase 3 — Fill in skipped specialists with instant "none" results.
  Phase 4 — Synthesis (with retries): strategy + DB persist.

IMPORTANT: Generator function (yield, no async/await) — required by the Durable SDK.
"""

from __future__ import annotations

import azure.durable_functions as df

from app.agents.specialists import ALL_SPECIALISTS
from durable.models import (
    CaseInput,
    EligibilityGateInput,
    EligibilityGateResult,
    SpecialistInput,
    SpecialistResult,
    SynthesisInput,
    SynthesisResult,
)

# All doc_keys in deterministic order (matches ALL_SPECIALISTS list order).
ALL_DOC_KEYS: list[str] = [cls.doc_key for cls in ALL_SPECIALISTS]

# doc_key → display program name.
_DOC_KEY_TO_PROGRAM: dict[str, str] = {cls.doc_key: cls.program for cls in ALL_SPECIALISTS}

# Retry configuration for synthesis — only the DB write inside synthesis is retryable.
SYNTHESIS_RETRY = df.RetryOptions(
    first_retry_interval_in_milliseconds=8_000,
    max_number_of_attempts=3,
)



def eligibility_orchestrator(context: df.DurableOrchestrationContext):
    """Gate → specialist fan-out → synthesis."""
    inp = CaseInput.model_validate(context.get_input())

    # ── Phase 1: Gate fan-out (all specialists in parallel) ───────────────────
    gate_tasks = [
        context.call_activity(
            "eligibility_gate",
            input_=EligibilityGateInput(
                doc_key=dk,
                profile_json=inp.profile_json,
            ).model_dump(),
        )
        for dk in ALL_DOC_KEYS
    ]
    gate_results_raw = yield context.task_all(gate_tasks)
    gates: dict[str, EligibilityGateResult] = {
        r["doc_key"]: EligibilityGateResult.model_validate(r)
        for r in gate_results_raw
    }
    active_keys = [dk for dk in ALL_DOC_KEYS if not gates[dk].skip]

    # ── Phase 2: First-pass specialist fan-out (all active, parallel) ─────────
    # Activities never raise — task_all is safe here.
    if active_keys:
        first_pass_tasks = [
            context.call_activity(
                "specialist_activity",
                input_=SpecialistInput(
                    doc_key=dk,
                    profile_json=inp.profile_json,
                ).model_dump(),
            )
            for dk in active_keys
        ]
        first_pass_raw = yield context.task_all(first_pass_tasks)
        first_pass: dict[str, SpecialistResult] = {
            r["doc_key"]: SpecialistResult.model_validate(r)
            for r in first_pass_raw
        }
    else:
        first_pass = {}

    all_results: dict[str, SpecialistResult] = dict(first_pass)

    # ── Phase 3: Fill in skipped specialists as instant "none" results ────────
    for dk, gate in gates.items():
        if gate.skip:
            all_results[dk] = SpecialistResult(
                doc_key=dk,
                program=_DOC_KEY_TO_PROGRAM[dk],
                match_level="none",
                notes=[gate.reason] if gate.reason else [],
            )

    # ── Phase 4: Synthesis with retries ──────────────────────────────────────
    synthesis_input = SynthesisInput(
        case_id=inp.case_id,
        profile_json=inp.profile_json,
        specialist_results=list(all_results.values()),
    )
    synthesis_raw = yield context.call_activity_with_retry(
        "synthesis_activity",
        retry_options=SYNTHESIS_RETRY,
        input_=synthesis_input.model_dump(),
    )
    synthesis = SynthesisResult.model_validate(synthesis_raw)

    return {
        "case_id": inp.case_id,
        "strategy": synthesis.strategy,
        "failed_specialists": synthesis.failed_specialist_programs,
    }
