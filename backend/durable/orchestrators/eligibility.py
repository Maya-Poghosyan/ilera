"""Main eligibility orchestrator.

Coordinates the full fan-out/fan-in eligibility assessment pipeline:

  Phase 1 — Gate fan-out:
    Run all specialist gate checks in parallel.  Gates are fast, deterministic,
    and never fail — any gate exception conservatively returns skip=False.

  Phase 2 — First-pass specialist fan-out:
    Run all active (non-skipped) specialist activities in parallel.  Activities
    never raise, so task_all completes even when individual specialists degrade.

  Phase 3 — Peer queries (optional):
    For each specialist that named cross_programs, resolve the target doc_key,
    spin up peer_query sub-orchestrations in parallel per target, then re-run
    the asking specialist with the peer answers injected.

  Phase 4 — Fill in skipped specialists:
    Skipped programs get an instant "none" SpecialistResult so synthesis always
    receives a complete set.

  Phase 5 — Synthesis (with retries):
    call_activity_with_retry ensures transient DB failures on the synthesis write
    are automatically retried without replaying the specialist fan-out.

IMPORTANT: This is a generator function (yield, no async/await, no async def) as
required by the Python Durable Functions SDK.
"""

from __future__ import annotations

import azure.durable_functions as df

from app.agents.specialists import ALL_SPECIALISTS
from durable.models import (
    CaseInput,
    EligibilityGateInput,
    EligibilityGateResult,
    PeerQueryInput,
    PeerQueryResult,
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


def _resolve_doc_key(program_name: str) -> str | None:
    """Map a program display name (from cross_programs) to its doc_key.

    Tries exact match first (case-insensitive), then substring match, so
    'Medi-Cal' → 'medical', 'VA Caregiver Support' → 'va', etc.
    """
    if not program_name:
        return None
    pn = program_name.strip().lower()
    # Exact match on doc_key or program name.
    for cls in ALL_SPECIALISTS:
        inst = cls()
        if pn in (inst.doc_key.lower(), inst.program.lower()):
            return inst.doc_key
    # Substring match (handles partial names like "IHSS" in "IHSS provider wage").
    for cls in ALL_SPECIALISTS:
        inst = cls()
        if pn in inst.program.lower() or inst.program.lower() in pn:
            return inst.doc_key
    return None


def eligibility_orchestrator(context: df.DurableOrchestrationContext):
    """Main orchestrator: gate → fan-out → peer queries → synthesis.

    Input: CaseInput (dict with case_id and profile_json)
    Returns: dict with case_id, strategy, failed_specialists
    """
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

    # ── Phase 3: Peer queries ─────────────────────────────────────────────────
    # For each first-pass result that named cross_programs, resolve target doc_keys,
    # run peer_query sub-orchestrations, then re-run the asking specialist with the
    # answers injected.  Yield tasks individually so a single peer failure does not
    # abort the others (task_all raises on first failure; we want partial results).
    all_results: dict[str, SpecialistResult] = dict(first_pass)

    for dk, result in list(first_pass.items()):
        if not result.cross_programs:
            continue

        peer_answers: dict[str, PeerQueryResult] = {}
        peer_task_list: list = []
        peer_target_keys: list[str] = []

        for cross_program in result.cross_programs:
            target_key = _resolve_doc_key(cross_program)
            if (
                target_key is None
                or target_key == dk
                or target_key not in active_keys
            ):
                continue
            child_id = f"{context.instance_id}-peer-{dk}-{target_key}"
            peer_task_list.append(
                context.call_sub_orchestrator(
                    "peer_query_orchestrator",
                    input_=PeerQueryInput(
                        asking_doc_key=dk,
                        target_doc_key=target_key,
                        question=(
                            f"How does {cross_program} affect "
                            f"{result.program} eligibility for this case?"
                        ),
                        profile_json=inp.profile_json,
                    ).model_dump(),
                    instance_id=child_id,
                )
            )
            peer_target_keys.append(target_key)

        if not peer_task_list:
            continue

        # Yield each peer task individually to handle partial failures gracefully.
        for target_key, task in zip(peer_target_keys, peer_task_list):
            try:
                raw = yield task
                peer_answers[target_key] = PeerQueryResult.model_validate(raw)
            except Exception as exc:
                peer_answers[target_key] = PeerQueryResult(
                    answer="",
                    peer_error={
                        "code": "PEER_ACTIVITY_ERROR",
                        "step": "peer_query_orchestrator",
                        "detail": str(exc),
                        "target": target_key,
                    },
                )

        # Re-run the asking specialist with peer answers.
        rerun_raw = yield context.call_activity(
            "specialist_activity",
            input_=SpecialistInput(
                doc_key=dk,
                profile_json=inp.profile_json,
                peer_answers=peer_answers,
            ).model_dump(),
        )
        all_results[dk] = SpecialistResult.model_validate(rerun_raw)

    # ── Phase 4: Fill in skipped specialists as instant "none" results ────────
    for dk, gate in gates.items():
        if gate.skip:
            all_results[dk] = SpecialistResult(
                doc_key=dk,
                program=_DOC_KEY_TO_PROGRAM[dk],
                match_level="none",
                notes=[gate.reason] if gate.reason else [],
            )

    # ── Phase 5: Synthesis with retries ──────────────────────────────────────
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
