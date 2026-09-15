"""Eligibility gate activity.

Runs a fast, pure-Python gate check for one specialist program.  The gate determines
whether the program is clearly ineligible for this case profile — if so, the specialist
LLM activity is skipped entirely.

Design:
- NEVER raises.  Any unexpected exception is caught and returned as gate_error=...,
  skip=False (conservative: let the specialist run rather than wrongly disqualifying).
- The activity is deliberately lightweight: no I/O, no network calls.  It is kept as
  a Durable activity (rather than inline orchestrator code) so the execution history
  shows the gate decision for every program, aiding debugging.
"""

from __future__ import annotations

import logging

from app.models import CaseProfile
from durable.errors import GateError
from durable.models import EligibilityGateInput, EligibilityGateResult
from durable.tools.eligibility_checks import GATES

logger = logging.getLogger(__name__)


async def eligibility_gate(payload: dict) -> dict:
    """Activity: run the eligibility gate for one specialist program.

    Input (payload):
        doc_key      str  — program identifier (ihss, medical, pfl, va, medicare, tax)
        profile_json str  — JSON-serialised CaseProfile

    Returns:
        EligibilityGateResult.model_dump()
    """
    inp = EligibilityGateInput.model_validate(payload)
    doc_key = inp.doc_key

    try:
        profile = CaseProfile.model_validate_json(inp.profile_json)
    except Exception as exc:
        logger.warning(
            "eligibility_gate: failed to deserialize profile for doc_key=%s: %s",
            doc_key,
            exc,
        )
        # Conservative: if we can't read the profile, let the specialist try.
        return EligibilityGateResult(
            doc_key=doc_key,
            skip=False,
            gate_error={
                "code": "PROFILE_DESERIALIZATION_ERROR",
                "step": "eligibility_gate",
                "doc_key": doc_key,
                "detail": str(exc),
            },
        ).model_dump()

    gate_fn = GATES.get(doc_key)
    if gate_fn is None:
        logger.warning("eligibility_gate: no gate function registered for doc_key=%s", doc_key)
        return EligibilityGateResult(
            doc_key=doc_key,
            skip=False,
            gate_error={
                "code": "GATE_ERROR",
                "step": "eligibility_gate",
                "doc_key": doc_key,
                "detail": f"No gate function registered for doc_key '{doc_key}'",
            },
        ).model_dump()

    try:
        skip, reason, fast_match_level = gate_fn(profile)
    except Exception as exc:
        err = GateError(
            str(exc),
            step="eligibility_gate",
            doc_key=doc_key,
        )
        logger.warning(
            "eligibility_gate: gate function raised for doc_key=%s: %s", doc_key, err
        )
        # Conservative fallback: skip=False so the specialist runs.
        return EligibilityGateResult(
            doc_key=doc_key,
            skip=False,
            gate_error=err.to_record(),
        ).model_dump()

    if skip:
        logger.info("eligibility_gate: skipping doc_key=%s reason=%r", doc_key, reason)

    return EligibilityGateResult(
        doc_key=doc_key,
        skip=skip,
        reason=reason,
        fast_match_level=fast_match_level,  # type: ignore[arg-type]
    ).model_dump()
