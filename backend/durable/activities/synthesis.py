"""Synthesis activity.

Aggregates all specialist results into a final application strategy and persists the
complete findings to the database.  This is the only activity in the pipeline that
intentionally raises (FindingsPersistenceError) — DB write failures are retryable at
the Durable level, and idempotent because save_profile overwrites by case_id.

Phases:
  1. Deserialise inputs and build SpecialistFinding objects.
  2. Persist findings to DB — raises FindingsPersistenceError if this fails (Durable retries).
  3. Run LLM strategy synthesis.  Falls back to a structured bullet list on LLM failure.
  4. Run analyze_program_interactions for cross-program interaction notes.
  5. Persist strategy + mark case complete.
  6. Return SynthesisResult.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.agents.interactions import analyze_program_interactions
from app.config import get_settings
from app.models import CaseProfile, SpecialistFinding
from app.store import finding_to_result, get_profile, save_profile
from app.strategy_text import format_strategy
from durable.errors import FindingsPersistenceError
from durable.models import SpecialistResult, SynthesisInput, SynthesisResult

logger = logging.getLogger(__name__)

# MatchLevel values valid in app/models.py (does NOT include "assessment_failed").
_VALID_MATCH_LEVELS = {"none", "low", "medium", "likely", "very_likely"}

_SYNTHESIS_SYSTEM = """\
You are Ilera's application strategy coordinator. Given specialist eligibility findings,
produce a concise application strategy as a plain bulleted list (at most 7 bullets, one per line,
each starting with "- "). Order by match strength: strongest programs first. Each bullet names
the program and one concrete next step. No headers, no markdown, no attribution, no disclaimers.\
"""


# ── Helpers ────────────────────────────────────────────────────────────────────


def _safe_match_level(match_level: str) -> str:
    """Map 'assessment_failed' and any unknown value to 'none' for DB storage."""
    return match_level if match_level in _VALID_MATCH_LEVELS else "none"


def _build_fallback_strategy(results: list[SpecialistResult]) -> str:
    """Construct a structured bullet strategy directly from match levels."""
    # Order by match strength (highest first).
    _ORDER = {"very_likely": 0, "likely": 1, "medium": 2, "low": 3, "none": 4, "assessment_failed": 5}
    sorted_results = sorted(results, key=lambda r: _ORDER.get(r.match_level, 5))

    bullets: list[str] = []
    for r in sorted_results:
        if r.match_level in {"none", "assessment_failed"}:
            continue
        level_label = {
            "very_likely": "Very likely eligible",
            "likely": "Likely eligible",
            "medium": "Possibly eligible",
            "low": "Low likelihood, worth checking",
        }.get(r.match_level, r.match_level)
        bullets.append(f"- {r.program}: {level_label} — apply and confirm eligibility")

    if not bullets:
        bullets.append("- Review eligibility with a benefits counselor for personalized guidance")

    return "\n".join(bullets[:7])


def _build_synthesis_user_prompt(results: list[SpecialistResult]) -> str:
    """Build the user prompt for LLM synthesis."""
    lines: list[str] = ["SPECIALIST ELIGIBILITY FINDINGS:"]
    for r in results:
        if r.match_level == "assessment_failed":
            lines.append(f"  {r.program}: assessment failed (could not determine eligibility)")
        else:
            note_summary = "; ".join(r.notes[:2]) if r.notes else "no notes"
            lines.append(f"  {r.program}: match_level={r.match_level} — {note_summary}")
    lines.append("\nProduce a plain bulleted application strategy (at most 7 bullets).")
    return "\n".join(lines)


def _error_record(*, code: str, step: str, detail: str, used_fallback: bool, failed_specialists: list[str]) -> dict:
    return {
        "code": code,
        "step": step,
        "detail": detail,
        "used_fallback": used_fallback,
        "failed_specialists": failed_specialists,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Activity ───────────────────────────────────────────────────────────────────


async def synthesis_activity(payload: dict) -> dict:
    """Activity: persist findings, synthesise strategy, persist strategy.

    Input (payload): SynthesisInput fields as a dict.
    Returns: SynthesisResult.model_dump()

    Raises:
        FindingsPersistenceError — DB write failure (retryable at Durable level).
    """
    inp = SynthesisInput.model_validate(payload)
    specialist_results = inp.specialist_results

    # ── Deserialise profile ────────────────────────────────────────────────────
    try:
        profile = CaseProfile.model_validate_json(inp.profile_json)
    except Exception as exc:
        logger.error("synthesis_activity: profile deserialization failed: %s", exc)
        # Cannot persist without a profile; raise so Durable retries.
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
        # Load the current profile from store; it may have been updated since orchestration
        # started.  Fall back to the in-flight profile if not found in the store yet.
        stored = get_profile(inp.case_id) or profile
        stored.findings.update(findings)
        stored.band_status = "processing"
        stored.band_started_at = stored.band_started_at or now
        # Also project findings into the legacy eligibility map.
        for dk, finding in findings.items():
            stored.eligibility[finding.program] = finding_to_result(finding)
        save_profile(stored)
        profile = stored  # use the freshly-updated profile for subsequent steps
    except Exception as exc:
        logger.error("synthesis_activity: findings persistence failed: %s", exc, exc_info=True)
        raise FindingsPersistenceError(
            str(exc),
            step="synthesis_activity.persist_findings",
            case_id=inp.case_id,
        ) from exc

    # ── Phase 3: LLM strategy synthesis ──────────────────────────────────────
    strategy_raw: str = ""
    synthesis_error_record: dict | None = None
    failed_programs: list[str] = [
        sr.program for sr in specialist_results if sr.fully_failed
    ]

    s = get_settings()
    if s.has_llm:
        try:
            from openai import AsyncOpenAI
            from pydantic_ai import Agent
            from pydantic_ai.models.openai import OpenAIModel

            openai_client = AsyncOpenAI(
                api_key=s.openai_api_key,
                base_url=s.openai_base_url or None,
                max_retries=6,
                timeout=90.0,
            )
            model = OpenAIModel(s.openai_model, openai_client=openai_client)
            agent: Agent[None, str] = Agent(
                model=model,
                output_type=str,
                system_prompt=_SYNTHESIS_SYSTEM,
            )
            user_prompt = _build_synthesis_user_prompt(specialist_results)
            result = await agent.run(user_prompt)
            strategy_raw = result.output or ""
        except Exception as exc:
            logger.warning("synthesis_activity: LLM synthesis failed: %s", exc, exc_info=True)
            synthesis_error_record = _error_record(
                code="SYNTHESIS_LLM_ERROR",
                step="synthesis_activity.llm",
                detail=str(exc),
                used_fallback=True,
                failed_specialists=failed_programs,
            )
            strategy_raw = ""
    else:
        logger.info("synthesis_activity: no LLM key, using fallback strategy")
        synthesis_error_record = _error_record(
            code="NO_LLM_KEY",
            step="synthesis_activity.llm",
            detail="LLM key not configured; using heuristic strategy",
            used_fallback=True,
            failed_specialists=failed_programs,
        )

    # Fall back to structured bullet list if LLM failed or produced nothing.
    if not strategy_raw or not strategy_raw.strip():
        strategy_raw = _build_fallback_strategy(specialist_results)

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
        # Non-fatal: strategy is still complete without interaction notes.

    # ── Phase 5: Persist strategy + mark case complete ────────────────────────
    try:
        profile.strategy = strategy
        profile.strategy_complete = True
        profile.band_status = "complete"
        profile.band_completed_at = datetime.now(timezone.utc).isoformat()
        save_profile(profile)
    except Exception as exc:
        logger.error("synthesis_activity: strategy persistence failed: %s", exc, exc_info=True)
        raise FindingsPersistenceError(
            str(exc),
            step="synthesis_activity.persist_strategy",
            case_id=inp.case_id,
        ) from exc

    # ── Collect partial failures for the frontend warning ─────────────────────
    degraded_programs = [
        sr.program
        for sr in specialist_results
        if sr.error_record is not None
    ]

    return SynthesisResult(
        strategy=strategy,
        interaction_notes=interaction_notes,
        failed_specialist_programs=degraded_programs,
        error_record=synthesis_error_record,
    ).model_dump()
