"""Base specialist agent.

Each specialist evaluates one benefits program. It performs RAG over the program's
official docs and, when an LLM key is configured, asks the model for a grounded
EligibilityResult. Without a key it falls back to the program's heuristic.
"""

from abc import ABC, abstractmethod

from .. import llm
from ..models import Citation, CaseProfile, EligibilityResult, FollowupQuestion
from ..rag.index import get_index


def _citations(hits) -> list[Citation]:
    """De-duplicate retrieved chunks down to one citation per source document."""
    seen: dict[str, Citation] = {}
    for h in hits:
        key = h.document_id or h.source
        if key and key not in seen:
            seen[key] = Citation(
                document_id=h.document_id or h.source,
                title=h.title or h.source,
                source_url=h.source_url,
                page=h.page,
                program=h.program,
            )
    return list(seen.values())


_SYSTEM = (
    "You are a benefits eligibility specialist helping unpaid family caregivers. "
    "You assess eligibility for ONE program using the caregiver's CaseProfile and the "
    "provided official program documentation. Ground every claim in the documentation; "
    "do not invent program rules. Respond with a SINGLE JSON object and nothing else."
)

_SCHEMA_HINT = """Return JSON with exactly these keys:
{
  "confidence": float 0..1,
  "status": one of "likely" | "possible" | "unlikely" | "needs_info",
  "rationale": short string grounded in the docs,
  "roadblocks": [string],
  "required_documents": [string],
  "next_steps": [string],
  "missing_info": [string],
  "followups": [{"id": string, "prompt": string, "type": "short_text"|"long_text"|"select"|"multiselect"|"boolean", "options": [string], "why": string}]
}
Only ask followups for information not already present in the CaseProfile."""


class SpecialistAgent(ABC):
    program: str
    doc_key: str  # matches the program_docs/<doc_key>.txt filename

    def retrieve(self, query: str, k: int = 4):
        return get_index().search(query, k=k, program=self.doc_key)

    def _sources(self, query: str) -> list[str]:
        return sorted({(r.title or r.source) for r in self.retrieve(query)})

    def _citations(self, query: str) -> list[Citation]:
        return _citations(self.retrieve(query))

    @abstractmethod
    def _heuristic_assess(self, profile: CaseProfile) -> EligibilityResult: ...

    def assess(self, profile: CaseProfile) -> EligibilityResult:
        if llm.available():
            try:
                return self._llm_assess(profile)
            except Exception:
                # Any LLM/parse failure degrades gracefully to the heuristic.
                return self._heuristic_assess(profile)
        return self._heuristic_assess(profile)

    def _llm_assess(self, profile: CaseProfile) -> EligibilityResult:
        hits = self.retrieve(f"{self.program} eligibility requirements and application", k=6)
        context = "\n\n".join(
            f"[{h.title or h.source}" + (f", p.{h.page}" if h.page else "") + f"] {h.text}"
            for h in hits
        ) or "(no documentation found)"
        user = (
            f"PROGRAM: {self.program}\n\n"
            f"OFFICIAL DOCUMENTATION:\n{context}\n\n"
            f"CAREGIVER CASE PROFILE (JSON):\n{profile.model_dump_json(indent=2)}\n\n"
            f"{_SCHEMA_HINT}"
        )
        data = llm.complete_json(_SYSTEM, user)
        followups = [
            FollowupQuestion(
                program=self.program,
                id=str(f.get("id", f"{self.doc_key}_{i}")),
                prompt=str(f.get("prompt", "")),
                type=f.get("type", "short_text"),
                options=list(f.get("options", []) or []),
                why=str(f.get("why", "")),
            )
            for i, f in enumerate(data.get("followups", []) or [])
            if f.get("prompt")
        ]
        return EligibilityResult(
            program=self.program,
            confidence=float(data.get("confidence", 0.0)),
            status=data.get("status", "needs_info"),
            rationale=str(data.get("rationale", "")),
            roadblocks=[str(x) for x in data.get("roadblocks", []) or []],
            required_documents=[str(x) for x in data.get("required_documents", []) or []],
            next_steps=[str(x) for x in data.get("next_steps", []) or []],
            missing_info=[str(x) for x in data.get("missing_info", []) or []],
            followups=followups,
            sources=sorted({(h.title or h.source) for h in hits}),
            citations=_citations(hits),
        )
