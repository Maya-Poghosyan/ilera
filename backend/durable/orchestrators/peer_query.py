"""Peer-query sub-orchestrator.

Routes a cross-program question from one specialist to another and condenses the
target specialist's full assessment into a short answer the asking specialist can use.

This is a sub-orchestration (called by the eligibility orchestrator) rather than a
direct activity call so that:
  - The child orchestration has its own replay-safe execution history.
  - Failures are isolated: a peer-query failure does not propagate the exception up
    through task_all; instead the eligibility orchestrator catches it and records a
    PeerQueryResult with peer_error set.
  - Child IDs are deterministic (parent_id + asking_key + target_key) so a replayed
    parent never spawns duplicate children.

IMPORTANT: This is a generator function (yield, no async/await, no async def) as
required by the Python Durable Functions SDK.
"""

from __future__ import annotations

import azure.durable_functions as df

from durable.models import PeerQueryInput, PeerQueryResult, SpecialistInput, SpecialistResult


def peer_query_orchestrator(context: df.DurableOrchestrationContext):
    """Sub-orchestrator: run a specialist and condense the answer for a peer query.

    Input: PeerQueryInput (dict)

    The question from the asking specialist is injected as a special peer_answers
    entry with key '_question_from_{asking_doc_key}'.  The target specialist's
    activity reads this key and formats it as "you are being asked: {question}" in
    its user prompt.

    Returns: PeerQueryResult.model_dump()
    """
    inp = PeerQueryInput.model_validate(context.get_input())

    # Inject the peer question into the target specialist's peer_answers so the
    # target knows it is answering a specific cross-program question.
    specialist_input = SpecialistInput(
        doc_key=inp.target_doc_key,
        profile_json=inp.profile_json,
        peer_answers={
            f"_question_from_{inp.asking_doc_key}": PeerQueryResult(
                answer=inp.question,
                citations=[],
            )
        },
    )

    raw = yield context.call_activity(
        "specialist_activity",
        input_=specialist_input.model_dump(),
    )

    result = SpecialistResult.model_validate(raw)

    # Condense the full assessment into a short answer the asking specialist can use.
    if result.notes:
        answer_text = " ".join(result.notes[:2])
    else:
        answer_text = f"match_level={result.match_level}"

    return PeerQueryResult(
        answer=f"[{result.program}] {answer_text}",
        citations=result.citations[:3],
        peer_error=result.error_record if result.fully_failed else None,
    ).model_dump()
