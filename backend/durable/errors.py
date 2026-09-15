"""Structured errors for the Durable Functions eligibility pipeline.

Design principles:
- Every error carries enough context to diagnose the failure from the Durable
  execution history alone (step, specialist, attempt, root cause).
- `retryable=True` errors are raised from activities so Durable's RetryOptions
  can retry them (network failures, rate limits, transient DB errors).
- `retryable=False` errors are caught inside activities and returned as a
  structured SpecialistResult / SynthesisResult with an error record attached —
  they represent logic failures that retrying won't fix (bad JSON, unknown key).
- No specialist failure sinks the whole orchestration; the orchestrator degrades
  gracefully and records exactly what failed and why.
"""

from __future__ import annotations

import json
from typing import Any


class IleraError(Exception):
    """Base class. Serializes structured context into the exception message so it
    surfaces verbatim in Durable's execution history and Azure Monitor logs."""

    code: str = "ILERA_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        step: str,
        doc_key: str | None = None,
        **context: Any,
    ) -> None:
        self.step = step
        self.doc_key = doc_key
        self.extra = context
        # Build a structured log line: "[CODE] step=X | specialist=Y | k=v | message"
        parts: list[str] = [f"[{self.code}]", f"step={step}"]
        if doc_key:
            parts.append(f"specialist={doc_key}")
        for k, v in context.items():
            parts.append(f"{k}={v}")
        parts.append(message)
        super().__init__(" | ".join(parts))

    def to_record(self) -> dict[str, Any]:
        """Serializable dict for embedding in SpecialistErrorRecord / SynthesisErrorRecord."""
        return {
            "code": self.code,
            "step": self.step,
            "doc_key": self.doc_key,
            "retryable": self.retryable,
            "detail": str(self),
            **self.extra,
        }


# ── Orchestrator errors ────────────────────────────────────────────────────────


class CaseNotFoundError(IleraError):
    """case_id passed to the orchestrator does not exist in the store."""
    code = "CASE_NOT_FOUND"
    # Not retryable — the case is simply missing; retrying won't create it.


class ProfileDeserializationError(IleraError):
    """profile_json passed to the orchestrator is not valid CaseProfile JSON."""
    code = "PROFILE_DESERIALIZATION_ERROR"


# ── Gate activity errors ───────────────────────────────────────────────────────


class GateError(IleraError):
    """Unexpected failure in a deterministic eligibility gate.

    These functions are pure Python with no I/O; this should never trigger.
    If it does, the orchestrator treats it as skip=False (conservative: let the
    specialist run rather than silently disqualify).
    """
    code = "GATE_ERROR"


# ── Specialist activity errors ─────────────────────────────────────────────────


class RagRetrievalError(IleraError):
    """pgvector search failed for a specialist's program scope.

    Retryable — likely a transient DB connection issue.
    If retries exhaust, the specialist falls back to heuristic with an empty
    context (which is what happens today when no docs are found).
    """
    code = "RAG_RETRIEVAL_ERROR"
    retryable = True


class LLMCallError(IleraError):
    """OpenAI / Azure OpenAI API call failed after the SDK's internal retries.

    Retryable at the Durable level — may be a rate-limit spike or transient
    Azure endpoint issue that the SDK retry budget didn't cover.
    """
    code = "LLM_CALL_ERROR"
    retryable = True


class LLMParseError(IleraError):
    """LLM response is not valid JSON.

    NOT retryable — if the model returned malformed JSON once it may do so
    again; the activity catches this and falls back to the heuristic instead.
    """
    code = "LLM_PARSE_ERROR"


class LLMSchemaError(IleraError):
    """LLM response is valid JSON but fails field validation (missing required
    keys, wrong types, out-of-range values).

    NOT retryable — same reasoning as LLMParseError.
    """
    code = "LLM_SCHEMA_ERROR"


class HeuristicFallbackError(IleraError):
    """Both the LLM path and the heuristic fallback raised exceptions.

    This produces a match_level='none' result with an explicit error record.
    The caregiver sees 'could not assess {program}' rather than a silent gap.
    """
    code = "HEURISTIC_FALLBACK_ERROR"


# ── Peer query errors ──────────────────────────────────────────────────────────


class UnknownPeerTargetError(IleraError):
    """A specialist named a cross_program that cannot be resolved to a doc_key.

    The orchestrator skips this peer query and proceeds without the answer.
    """
    code = "UNKNOWN_PEER_TARGET"


class PeerActivityError(IleraError):
    """The target specialist activity failed during a peer query sub-orchestration.

    The orchestrator proceeds without the peer answer and notes the degradation
    in the asking specialist's result.
    """
    code = "PEER_ACTIVITY_ERROR"


# ── Synthesis activity errors ──────────────────────────────────────────────────


class SynthesisLLMError(IleraError):
    """LLM call for strategy synthesis failed after retries.

    Retryable — synthesis is attempted once per case and is worth a retry.
    After retry exhaustion the activity falls back to a structured bullet list
    built directly from SpecialistResult.match_level values.
    """
    code = "SYNTHESIS_LLM_ERROR"
    retryable = True


class SynthesisParseError(IleraError):
    """Synthesis LLM response cannot be parsed or formatted.

    NOT retryable — falls back to structured bullet list immediately.
    """
    code = "SYNTHESIS_PARSE_ERROR"


class FindingsPersistenceError(IleraError):
    """DB write for findings or strategy failed.

    Retryable — Durable will retry the synthesis activity, which re-attempts
    the write. Idempotent because save_profile overwrites by case_id.
    """
    code = "FINDINGS_PERSISTENCE_ERROR"
    retryable = True


class PartialSynthesisWarning(IleraError):
    """Synthesis succeeded but one or more specialists produced error results.

    Not an exception in the control-flow sense — recorded in SynthesisResult
    as a warning so the frontend can surface 'some programs could not be assessed'.
    """
    code = "PARTIAL_SYNTHESIS"


# ── Error records (embedded in activity results) ───────────────────────────────


class SpecialistErrorRecord:
    """Embedded in SpecialistResult when a specialist partially or fully failed.

    Carries the full error chain so the synthesis activity and the frontend can
    explain exactly what went wrong for a given program.
    """

    __slots__ = ("code", "step", "detail", "used_heuristic", "llm_attempted", "timestamp")

    def __init__(
        self,
        *,
        code: str,
        step: str,
        detail: str,
        used_heuristic: bool,
        llm_attempted: bool,
        timestamp: str,
    ) -> None:
        self.code = code
        self.step = step
        self.detail = detail
        self.used_heuristic = used_heuristic
        self.llm_attempted = llm_attempted
        self.timestamp = timestamp

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "step": self.step,
            "detail": self.detail,
            "used_heuristic": self.used_heuristic,
            "llm_attempted": self.llm_attempted,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_error(
        cls,
        err: IleraError,
        *,
        used_heuristic: bool,
        llm_attempted: bool,
    ) -> "SpecialistErrorRecord":
        from datetime import datetime, timezone
        return cls(
            code=err.code,
            step=err.step,
            detail=str(err),
            used_heuristic=used_heuristic,
            llm_attempted=llm_attempted,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


class SynthesisErrorRecord:
    """Embedded in SynthesisResult when synthesis degraded or partially failed."""

    __slots__ = ("code", "step", "detail", "used_fallback", "failed_specialists", "timestamp")

    def __init__(
        self,
        *,
        code: str,
        step: str,
        detail: str,
        used_fallback: bool,
        failed_specialists: list[str],
        timestamp: str,
    ) -> None:
        self.code = code
        self.step = step
        self.detail = detail
        self.used_fallback = used_fallback
        self.failed_specialists = failed_specialists
        self.timestamp = timestamp

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "step": self.step,
            "detail": self.detail,
            "used_fallback": self.used_fallback,
            "failed_specialists": self.failed_specialists,
            "timestamp": self.timestamp,
        }
