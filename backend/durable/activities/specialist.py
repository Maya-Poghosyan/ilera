"""Specialist eligibility assessment activity.

Runs one specialist's full LLM-powered eligibility assessment using pydantic-ai.
The specialist uses a RAG tool to ground its reasoning in official program documentation
before producing a structured SpecialistResult.

If the LLM call fails for any reason, the activity returns match_level="assessment_failed"
with full error context — it does not fall back to heuristics.

The LLM reasons privately via tool calls (gate check + RAG). Only a clean one-sentence
summary is returned to the user — no raw reasoning, citations, or policy quotes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.specialists import ALL_SPECIALISTS
from app.config import get_settings
from app.models import CaseProfile, EligibilityResult, FollowupQuestion
from durable.models import PeerQueryResult, SpecialistInput, SpecialistResult
from durable.tools.eligibility_checks import make_gate_tool

logger = logging.getLogger(__name__)

# Map doc_key → program name for building SpecialistResult without instantiating.
_DOC_KEY_TO_PROGRAM: dict[str, str] = {cls.doc_key: cls.program for cls in ALL_SPECIALISTS}

# ── Pydantic-ai output schema ──────────────────────────────────────────────────


class _FollowupOutput(BaseModel):
    id: str
    prompt: str
    type: Literal["short_text", "long_text", "select", "multiselect", "boolean"] = "short_text"
    options: list[str] = Field(default_factory=list)
    why: str = ""


class _SpecialistOutput(BaseModel):
    """Structured output schema the LLM must conform to."""

    match_level: Literal["none", "low", "medium", "likely", "very_likely"]
    # User-facing one-liner. Must NOT contain citations, policy quotes, or program
    # descriptions. Plain English for a family caregiver — the LLM's reasoning stays
    # internal (tool calls / RAG); only the clean verdict reaches the user.
    summary: str = Field(
        default="",
        description=(
            "One sentence for the caregiver explaining why this program does or doesn't "
            "look like a fit — using only facts from THIS person's profile. "
            "No program descriptions. No citations. No jargon."
        ),
    )
    roadblocks: list[str] = Field(
        default_factory=list,
        description="Specific barriers for this person that would block or complicate the application.",
    )
    next_steps: list[str] = Field(
        default_factory=list,
        description="Concrete action items for the caregiver to pursue this program.",
    )
    required_documents: list[str] = Field(
        default_factory=list,
        description="Documents the applicant will need to submit.",
    )
    missing_info: list[str] = Field(
        default_factory=list,
        description="Information not in the profile that would change this assessment.",
    )
    followups: list[_FollowupOutput] = Field(
        default_factory=list,
        description="Questions to ask the caregiver to fill gaps in the profile.",
    )


# ── System prompt template ─────────────────────────────────────────────────────

_SYSTEM_TEMPLATE = """\
You are Ilera's eligibility specialist for {program}.
Assess ONLY {program} eligibility for the provided caregiver profile.

Step 1 — ALWAYS call check_program_gate first. If it returns INELIGIBLE, set \
match_level='none' and write a one-sentence summary explaining the disqualifying reason \
in plain English. Do not call any other tools.
Step 2 — If the gate returns ELIGIBLE, call lookup_program_docs to retrieve official \
program documentation. Use it to reason privately — do not quote or cite it in summary.
Step 3 — Return structured output:
- match_level: your eligibility confidence (none/low/medium/likely/very_likely)
- summary: ONE sentence for the caregiver. Use only facts from their profile. \
  No program descriptions, no citations, no jargon — just the reason this person \
  does or doesn't look like a fit.
- roadblocks: specific barriers for this person (short bullets, plain English)
- next_steps: concrete actions for the caregiver
- required_documents: documents they will need
- missing_info: profile gaps that would change your assessment
- followups: questions to fill those gaps\
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
                asking_key = key.removeprefix("_question_from_")
                parts.append(
                    f"  [Question from {asking_key} specialist] You are being asked: {pqr.answer}"
                )
            else:
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


_MATCH_TO_STATUS = {
    "none": ("unlikely", 0.05),
    "low": ("unlikely", 0.3),
    "medium": ("possible", 0.55),
    "likely": ("likely", 0.78),
    "very_likely": ("likely", 0.93),
}


def _eligibility_result_from_output(
    output: _SpecialistOutput, program: str,
) -> EligibilityResult:
    """Project _SpecialistOutput into a full EligibilityResult."""
    status, confidence = _MATCH_TO_STATUS.get(output.match_level, ("needs_info", 0.4))
    followups = [
        FollowupQuestion(
            program=program,
            id=f.id,
            prompt=f.prompt,
            type=f.type,
            options=f.options,
            why=f.why,
        )
        for f in output.followups
        if f.prompt
    ]
    return EligibilityResult(
        program=program,
        confidence=confidence,
        status=status,  # type: ignore[arg-type]
        match_level=output.match_level,
        rationale=output.summary,
        roadblocks=output.roadblocks,
        required_documents=output.required_documents,
        next_steps=output.next_steps,
        missing_info=output.missing_info,
        followups=followups,
        sources=[],
    )


# ── Activity ───────────────────────────────────────────────────────────────────


async def specialist_activity(payload: dict) -> dict:
    """Activity: run one specialist's LLM eligibility assessment.

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

    def _failed(code: str, detail: str) -> dict:
        return SpecialistResult(
            doc_key=doc_key,
            program=program,
            match_level="assessment_failed",
            error_record={
                "code": code,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        ).model_dump()

    # ── Deserialize profile ────────────────────────────────────────────────────
    try:
        profile = CaseProfile.model_validate_json(inp.profile_json)
    except Exception as exc:
        logger.error("specialist_activity: profile deserialization failed doc_key=%s: %s", doc_key, exc)
        return _failed("PROFILE_DESERIALIZATION_ERROR", str(exc))

    # ── LLM assessment ────────────────────────────────────────────────────────
    try:
        from openai import AsyncOpenAI
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from durable.tools.rag_tool import make_rag_tool

        s = get_settings()
        openai_client = AsyncOpenAI(
            api_key=s.openai_api_key,
            base_url=s.openai_base_url or None,
            max_retries=6,
            timeout=90.0,
        )
        model = OpenAIModel(s.openai_model, provider=OpenAIProvider(openai_client=openai_client))
        agent: Agent[CaseProfile, _SpecialistOutput] = Agent(
            model=model,
            output_type=_SpecialistOutput,
            system_prompt=_SYSTEM_TEMPLATE.format(program=program),
            tools=[make_gate_tool(doc_key), make_rag_tool(doc_key)],
            deps_type=CaseProfile,
            retries=2,
        )

        user_prompt = _build_user_prompt(profile, inp.peer_answers)
        result = await agent.run(user_prompt, deps=profile)
        llm_output = result.output

    except Exception as exc:
        logger.error(
            "specialist_activity: LLM failed for doc_key=%s: %s",
            doc_key, exc, exc_info=True,
        )
        return _failed("LLM_ERROR", str(exc))

    eligibility_result = _eligibility_result_from_output(llm_output, program)
    return SpecialistResult(
        doc_key=doc_key,
        program=program,
        match_level=llm_output.match_level,
        notes=[llm_output.summary] if llm_output.summary else [],
        eligibility_result_json=eligibility_result.model_dump_json(),
    ).model_dump()
