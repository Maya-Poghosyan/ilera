"""Base specialist agent. Each specialist evaluates one benefits program via RAG
and a deterministic heuristic fallback used when the LLM path fails."""

from abc import ABC, abstractmethod

from ..models import Citation, CaseProfile, EligibilityResult
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
