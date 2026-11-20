"""Structured errors for the Durable Functions eligibility pipeline.

Design principles:
- Every error carries enough context to diagnose the failure from the Durable
  execution history alone (step, specialist, attempt, root cause).
- `retryable=True` errors are raised from activities so Durable's RetryOptions
  can retry them (network failures, rate limits, transient DB errors).
- `retryable=False` errors are caught inside activities and returned as an error
  record on the activity result — logic failures that retrying won't fix.
"""

from __future__ import annotations

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
        """Serializable dict for embedding in an activity result."""
        return {
            "code": self.code,
            "step": self.step,
            "doc_key": self.doc_key,
            "retryable": self.retryable,
            "detail": str(self),
            **self.extra,
        }


class GateError(IleraError):
    """Unexpected failure in a deterministic eligibility gate.

    These functions are pure Python with no I/O; this should never trigger.
    If it does, the orchestrator treats it as skip=False (conservative: let the
    specialist run rather than silently disqualify).
    """
    code = "GATE_ERROR"


class FindingsPersistenceError(IleraError):
    """DB write for findings or strategy failed.

    Retryable — Durable will retry the synthesis activity, which re-attempts
    the write. Idempotent because save_profile overwrites by case_id.
    """
    code = "FINDINGS_PERSISTENCE_ERROR"
    retryable = True
