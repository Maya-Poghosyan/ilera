"""Synthesis activity.

Aggregates all specialist results into a final application strategy and persists the
complete findings to the database.  Raises FindingsPersistenceError on any failure —
DB write failures and LLM failures are both retryable at the Durable level.

Phases:
  1. Deserialise inputs and build SpecialistFinding objects.
  2. Persist findings to DB — raises FindingsPersistenceError if this fails.
  3. Run LLM strategy synthesis — raises FindingsPersistenceError if this fails.
  4. Run analyze_program_interactions for cross-program interaction notes.
  5. Persist strategy + mark case complete.
  6. Return SynthesisResult.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.agents.interactions import analyze_program_interactions
from app.config import get_settings
from app.models import CaseProfile, EligibilityResult, SpecialistFinding
from app.store import finding_to_result, get_profile, save_profile
from app.strategy_text import format_strategy
from durable.errors import FindingsPersistenceError
from durable.models import SpecialistResult, SynthesisInput, SynthesisResult

logger = logging.getLogger(__name__)

# MatchLevel values valid in app/models.py (does NOT include "assessment_failed").
_VALID_MATCH_LEVELS = {"none", "low", "medium", "likely", "very_likely"}

_SYNTHESIS_SYSTEM = """\
You are helping an unpaid family caregiver understand which benefits they may qualify for.
Given specialist eligibility findings, produce a plain bulleted list of at most 7 bullets
total (one per line, each starting with "- "). Skip programs with match_level "none".

Structure the bullets as follows:
1. One bullet per matched program, ordered strongest match first.
   Format: "- **{Program}:** {one plain-English sentence explaining why this looks like a match}"
2. If any programs have a dependency or must be applied for in a specific order, add a
   separate bullet for that — do not fold it into the program bullet.
   Format: "- **Heads up:** Start with {Program A} before applying for {Program B} — {one sentence why}"

Use simple, everyday language. No jargon, no policy citations, no technical terms.
Write as if explaining to someone with no benefits experience.
No next steps. No action items. No headers, no markdown, no attribution, no disclaimers.
The total number of bullets must not exceed 7.\
"""


# ── Helpers ────────────────────────────────────────────────────────────────────


def _safe_match_level(match_level: str) -> str:
    """Map 'assessment_failed' and any unknown value to 'none' for DB storage."""
    return match_level if match_level in _VALID_MATCH_LEVELS else "none"


def _build_synthesis_user_prompt(results: list[SpecialistResult]) -> str:
    lines: list[str] = ["SPECIALIST ELIGIBILITY FINDINGS:"]
    for r in results:
        if r.match_level == "assessment_failed":
            lines.append(f"  {r.program}: assessment failed (could not determine eligibility)")
        else:
            note_summary = "; ".join(r.notes[:2]) if r.notes else "no notes"
            lines.append(f"  {r.program}: match_level={r.match_level} — {note_summary}")
    lines.append("\nProduce a plain bulleted list: one bullet per matched program, each with one sentence of reasoning and a prioritization note where programs depend on each other.")
    return "\n".join(lines)


# ── Activity ───────────────────────────────────────────────────────────────────


async def synthesis_activity(payload: dict) -> dict:
    """Activity: persist findings, synthesise strategy, persist strategy.

    Input (payload): SynthesisInput fields as a dict.
    Returns: SynthesisResult.model_dump()

    Raises:
        FindingsPersistenceError — any failure (DB write or LLM); Durable retries.
    """
    inp = SynthesisInput.model_validate(payload)
    specialist_results = inp.specialist_results

    # ── Deserialise profile ────────────────────────────────────────────────────
    try:
        profile = CaseProfile.model_validate_json(inp.profile_json)
    except Exception as exc:
        logger.error("synthesis_activity: profile deserialization failed: %s", exc)
        raise FindingsPersistenceError(
            str(exc),
            step="synthesis_activity.deserialize",
            case_id=inp.case_id,
        ) from exc

    # ── Phase 1: Build SpecialistFinding objects ───────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    findings: dict[str, SpecialistFinding] = {}
    for sr in specialist_results:
        safe_ml = _safe_match_level(sr.match_level)
        finding = SpecialistFinding(
            program=sr.program,
            doc_key=sr.doc_key,
            match_level=safe_ml,  # type: ignore[arg-type]
            notes=sr.notes,
            cross_programs=sr.cross_programs,
            citations=sr.citations,
            complete=not sr.fully_failed,
            updated_at=now,
        )
        findings[sr.doc_key] = finding

    # ── Phase 2: Persist findings to DB ───────────────────────────────────────
    try:
        stored = get_profile(inp.case_id) or profile
        stored.findings.update(findings)
        stored.eligibility_status = "processing"
        stored.eligibility_started_at = stored.eligibility_started_at or now
        sr_by_doc_key = {sr.doc_key: sr for sr in specialist_results}
        for dk, finding in findings.items():
            sr = sr_by_doc_key.get(dk)
            if sr and sr.eligibility_result_json:
                try:
                    stored.eligibility[finding.program] = EligibilityResult.model_validate_json(
                        sr.eligibility_result_json
                    )
                    continue
                except Exception:
                    pass
            stored.eligibility[finding.program] = finding_to_result(finding)
        save_profile(stored)
        profile = stored
    except Exception as exc:
        logger.error("synthesis_activity: findings persistence failed: %s", exc, exc_info=True)
        raise FindingsPersistenceError(
            str(exc),
            step="synthesis_activity.persist_findings",
            case_id=inp.case_id,
        ) from exc

    # ── Phase 3: LLM strategy synthesis ──────────────────────────────────────
    try:
        from openai import AsyncOpenAI
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIModel
        from pydantic_ai.providers.openai import OpenAIProvider

        s = get_settings()
        openai_client = AsyncOpenAI(
            api_key=s.openai_api_key,
            base_url=s.openai_base_url or None,
            max_retries=6,
            timeout=90.0,
        )
        model = OpenAIModel(s.openai_model, provider=OpenAIProvider(openai_client=openai_client))
        agent: Agent[None, str] = Agent(
            model=model,
            output_type=str,
            system_prompt=_SYNTHESIS_SYSTEM,
        )
        result = await agent.run(_build_synthesis_user_prompt(specialist_results))
        strategy_raw = result.output or ""
    except Exception as exc:
        logger.error("synthesis_activity: LLM synthesis failed: %s", exc, exc_info=True)
        raise FindingsPersistenceError(
            str(exc),
            step="synthesis_activity.llm",
            case_id=inp.case_id,
        ) from exc

    strategy = format_strategy(strategy_raw)

    # ── Phase 4: Cross-program interaction notes ──────────────────────────────
    interaction_notes: list[str] = []
    try:
        active_programs = [
            sr.program
            for sr in specialist_results
            if sr.match_level not in {"none", "assessment_failed"}
        ]
        if len(active_programs) >= 2:
            notes = analyze_program_interactions(profile, active_programs)
            interaction_notes = [
                n.note + (f" {n.action}" if n.action else "")
                for n in notes
                if n.note
            ]
    except Exception as exc:
        logger.warning("synthesis_activity: interaction analysis failed: %s", exc)

    # ── Phase 5: Persist strategy + mark case complete ────────────────────────
    try:
        profile.strategy = strategy
        profile.strategy_complete = True
        profile.eligibility_status = "complete"
        profile.eligibility_completed_at = datetime.now(timezone.utc).isoformat()
        save_profile(profile)
    except Exception as exc:
        logger.error("synthesis_activity: strategy persistence failed: %s", exc, exc_info=True)
        raise FindingsPersistenceError(
            str(exc),
            step="synthesis_activity.persist_strategy",
            case_id=inp.case_id,
        ) from exc

    degraded_programs = [sr.program for sr in specialist_results if sr.error_record is not None]

    return SynthesisResult(
        strategy=strategy,
        interaction_notes=interaction_notes,
        failed_specialist_programs=degraded_programs,
    ).model_dump()
