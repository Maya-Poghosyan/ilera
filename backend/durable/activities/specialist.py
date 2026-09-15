"""Specialist eligibility assessment activity.

Runs one specialist's full LLM-powered eligibility assessment using pydantic-ai.
The specialist uses a RAG tool to ground its reasoning in official program documentation
before producing a structured SpecialistResult.

Error handling (layered, NEVER raises from the activity):
  1. LLM path: pydantic-ai Agent run with RAG tool.  If the model or SDK raises →
     catch, record llm_error, fall through to heuristic.
  2. Heuristic fallback: the specialist's deterministic `_heuristic_assess`.  If it
     succeeds → return result with error_record showing LLM failed, used_heuristic=True.
  3. Total failure: both paths failed → return SpecialistResult with
     match_level="assessment_failed" and full error context.

The activity also accepts peer_answers (set by the orchestrator after peer-query
sub-orchestrations) and injects them into the user prompt as additional context.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.specialists import ALL_SPECIALISTS
from app.config import get_settings
from app.models import CaseProfile, EligibilityResult
from app.store import finding_to_result
from app.models import SpecialistFinding
from durable.models import PeerQueryResult, SpecialistInput, SpecialistResult

logger = logging.getLogger(__name__)

# Map specialist class doc_key → class for fast lookup.
_REGISTRY: dict[str, type] = {cls.doc_key: cls for cls in ALL_SPECIALISTS}

# Map doc_key → program name for building SpecialistResult without instantiating.
_DOC_KEY_TO_PROGRAM: dict[str, str] = {cls.doc_key: cls.program for cls in ALL_SPECIALISTS}

# ── Pydantic-ai output schema ──────────────────────────────────────────────────


class _SpecialistOutput(BaseModel):
    """Structured output schema the LLM must conform to."""

    match_level: Literal["none", "low", "medium", "likely", "very_likely"]
    notes: list[str] = Field(
        default_factory=list,
        description="Grounded reasoning strings; each note cites a retrieved document.",
    )
    cross_programs: list[str] = Field(
        default_factory=list,
        description="Other programs this case should consider for cross-eligibility.",
    )
    citations: list[str] = Field(
        default_factory=list,
        description="Citation strings in format 'Title (page) — URL' or 'Title (page)'.",
    )


# ── System prompt template ─────────────────────────────────────────────────────

_SYSTEM_TEMPLATE = """\
You are Ilera's eligibility specialist for {program}.
Assess ONLY {program} eligibility for the provided caregiver profile.
Use the lookup_program_docs tool to retrieve official program documentation before assessing.
Ground every claim in retrieved documentation. Do not invent program rules.
Return structured output with match_level, notes (list of grounded reasoning strings),
cross_programs (other programs this case should consider), and citations (source titles/pages).\
"""


# ── Helpers ────────────────────────────────────────────────────────────────────


def _build_user_prompt(
    profile: CaseProfile,
    peer_answers: dict[str, PeerQueryResult],
) -> str:
    """Compose the user-turn prompt including profile JSON and any peer context."""
    parts: list[str] = [
        "CAREGIVER CASE PROFILE (JSON):",
        profile.model_dump_json(indent=2),
    ]

    if peer_answers:
        parts.append("\nCROSS-PROGRAM CONTEXT FROM PEER SPECIALISTS:")
        for key, pqr in peer_answers.items():
            if key.startswith("_question_from_"):
                # The orchestrator injected a question directed at this specialist.
                asking_key = key.removeprefix("_question_from_")
                parts.append(
                    f"  [Question from {asking_key} specialist] You are being asked: {pqr.answer}"
                )
            else:
                # An answer retrieved from another specialist.
                citations_str = (
                    " Citations: " + "; ".join(pqr.citations) if pqr.citations else ""
                )
                if pqr.peer_error:
                    parts.append(
                        f"  [{key}] Peer query failed — no answer available."
                    )
                else:
                    parts.append(f"  [{key}] {pqr.answer}{citations_str}")

    parts.append(
        "\nAssess eligibility for YOUR program only. "
        "Use lookup_program_docs before finalising your assessment."
    )
    return "\n".join(parts)


def _eligibility_result_from_output(
    output: _SpecialistOutput, program: str, doc_key: str
) -> EligibilityResult:
    """Project _SpecialistOutput into an EligibilityResult for the applications page."""
    # Reuse the same mapping the rest of the app uses.
    finding = SpecialistFinding(
        program=program,
        doc_key=doc_key,
        match_level=output.match_level,
        notes=output.notes,
        cross_programs=output.cross_programs,
        citations=output.citations,
        complete=True,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    return finding_to_result(finding)


def _error_record(
    *,
    code: str,
    step: str,
    detail: str,
    used_heuristic: bool,
    llm_attempted: bool,
) -> dict:
    return {
        "code": code,
        "step": step,
        "detail": detail,
        "used_heuristic": used_heuristic,
        "llm_attempted": llm_attempted,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Activity ───────────────────────────────────────────────────────────────────


async def specialist_activity(payload: dict) -> dict:
    """Activity: run one specialist's eligibility assessment.

    Input (payload):
        doc_key      str                        — program identifier
        profile_json str                        — JSON-serialised CaseProfile
        peer_answers dict[str, PeerQueryResult] — answers from peer-query sub-orchestrations

    Returns:
        SpecialistResult.model_dump()
    """
    inp = SpecialistInput.model_validate(payload)
    doc_key = inp.doc_key
    program = _DOC_KEY_TO_PROGRAM.get(doc_key, doc_key)

    # ── Deserialize profile ────────────────────────────────────────────────────
    try:
        profile = CaseProfile.model_validate_json(inp.profile_json)
    except Exception as exc:
        logger.error("specialist_activity: failed to deserialize profile doc_key=%s: %s", doc_key, exc)
        return SpecialistResult(
            doc_key=doc_key,
            program=program,
            match_level="assessment_failed",
            error_record=_error_record(
                code="PROFILE_DESERIALIZATION_ERROR",
                step="specialist_activity.deserialize",
                detail=str(exc),
                used_heuristic=False,
                llm_attempted=False,
            ),
        ).model_dump()

    specialist_cls = _REGISTRY.get(doc_key)
    if specialist_cls is None:
        return SpecialistResult(
            doc_key=doc_key,
            program=program,
            match_level="assessment_failed",
            error_record=_error_record(
                code="UNKNOWN_SPECIALIST",
                step="specialist_activity.lookup",
                detail=f"No specialist registered for doc_key '{doc_key}'",
                used_heuristic=False,
                llm_attempted=False,
            ),
        ).model_dump()

    specialist_instance = specialist_cls()

    # ── Attempt LLM path ──────────────────────────────────────────────────────
    llm_error: Exception | None = None
    llm_output: _SpecialistOutput | None = None

    s = get_settings()
    if s.has_llm:
        try:
            from openai import AsyncOpenAI
            from pydantic_ai import Agent
            from pydantic_ai.models.openai import OpenAIModel
            from durable.tools.rag_tool import make_rag_tool

            openai_client = AsyncOpenAI(
                api_key=s.openai_api_key,
                base_url=s.openai_base_url or None,
                max_retries=6,
                timeout=90.0,
            )
            model = OpenAIModel(s.openai_model, openai_client=openai_client)
            agent: Agent[CaseProfile, _SpecialistOutput] = Agent(
                model=model,
                output_type=_SpecialistOutput,
                system_prompt=_SYSTEM_TEMPLATE.format(program=program),
                tools=[make_rag_tool(doc_key)],
                deps_type=CaseProfile,
                max_retries=2,
            )

            user_prompt = _build_user_prompt(profile, inp.peer_answers)
            result = await agent.run(user_prompt, deps=profile)
            llm_output = result.output

        except Exception as exc:
            llm_error = exc
            logger.warning(
                "specialist_activity: LLM path failed for doc_key=%s: %s",
                doc_key,
                exc,
                exc_info=True,
            )
    else:
        logger.info(
            "specialist_activity: no LLM key configured, using heuristic for doc_key=%s",
            doc_key,
        )

    # LLM succeeded — build result.
    if llm_output is not None:
        eligibility_result = _eligibility_result_from_output(llm_output, program, doc_key)
        return SpecialistResult(
            doc_key=doc_key,
            program=program,
            match_level=llm_output.match_level,
            notes=llm_output.notes,
            cross_programs=llm_output.cross_programs,
            citations=llm_output.citations,
            eligibility_result_json=eligibility_result.model_dump_json(),
        ).model_dump()

    # ── Attempt heuristic fallback ─────────────────────────────────────────────
    heuristic_error: Exception | None = None
    heuristic_result: EligibilityResult | None = None

    try:
        heuristic_result = specialist_instance._heuristic_assess(profile)
    except Exception as exc:
        heuristic_error = exc
        logger.error(
            "specialist_activity: heuristic failed for doc_key=%s: %s", doc_key, exc
        )

    if heuristic_result is not None:
        # LLM failed but heuristic succeeded.
        llm_detail = str(llm_error) if llm_error else "LLM key not configured"
        return SpecialistResult(
            doc_key=doc_key,
            program=program,
            match_level=heuristic_result.match_level,
            notes=[heuristic_result.rationale] if heuristic_result.rationale else [],
            cross_programs=[],
            citations=[str(c.title or c.source_url) for c in heuristic_result.citations if c],
            eligibility_result_json=heuristic_result.model_dump_json(),
            error_record=_error_record(
                code="LLM_CALL_ERROR" if llm_error else "NO_LLM_KEY",
                step="specialist_activity.llm",
                detail=llm_detail,
                used_heuristic=True,
                llm_attempted=bool(llm_error),
            ),
        ).model_dump()

    # ── Total failure — both LLM and heuristic failed ─────────────────────────
    combined_detail = (
        f"LLM: {llm_error}; Heuristic: {heuristic_error}"
        if llm_error
        else f"Heuristic: {heuristic_error}"
    )
    logger.error(
        "specialist_activity: total failure for doc_key=%s: %s", doc_key, combined_detail
    )
    return SpecialistResult(
        doc_key=doc_key,
        program=program,
        match_level="assessment_failed",
        error_record=_error_record(
            code="HEURISTIC_FALLBACK_ERROR",
            step="specialist_activity.heuristic",
            detail=combined_detail,
            used_heuristic=False,
            llm_attempted=bool(llm_error),
        ),
    ).model_dump()
