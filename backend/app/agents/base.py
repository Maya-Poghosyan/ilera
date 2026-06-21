"""Base specialist agent.

Each specialist evaluates one benefits program. It performs RAG over the program's
official docs, then applies program-specific logic to produce an EligibilityResult.
The default `assess` uses lightweight heuristics; override per program. When an LLM key
is configured you can replace the heuristic with a grounded LLM call using `retrieve`.
"""

from abc import ABC, abstractmethod

from ..models import CaseProfile, EligibilityResult
from ..rag.index import get_index


class SpecialistAgent(ABC):
    program: str
    doc_key: str  # matches the program_docs/<doc_key>.txt filename

    def retrieve(self, query: str, k: int = 4):
        return get_index().search(query, k=k, program=self.doc_key)

    @abstractmethod
    def assess(self, profile: CaseProfile) -> EligibilityResult: ...

    def _sources(self, query: str) -> list[str]:
        return sorted({r.source for r in self.retrieve(query)})
