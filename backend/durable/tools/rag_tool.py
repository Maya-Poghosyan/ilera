"""RAG tool factory for pydantic-ai specialist agents.

`make_rag_tool(doc_key, scope)` returns an async function suitable for use as a pydantic-ai
tool.  Each returned function is scoped to its program's corpus slice, so the IHSS
specialist only retrieves IHSS documents, the VA specialist only VA documents, etc.

The function formats retrieved passages into a single string with inline citations
(title + page) that the LLM can reference in its structured output.

Retrieval failures raise so assessments cannot substitute general knowledge for
scoped policy evidence.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
import json

from app.rag.scope import RetrievalScope

logger = logging.getLogger(__name__)

# Maximum number of passages to retrieve per query.
_DEFAULT_K = 5


def make_rag_tool(doc_key: str, scope: RetrievalScope) -> Callable[..., str]:
    """Return a pydantic-ai-compatible async tool function scoped to *doc_key*.

    The returned coroutine's docstring is used by pydantic-ai as the tool description
    presented to the model, so it is intentionally in plain English.
    """

    if scope.program != doc_key:
        raise ValueError("Specialist and retrieval program must match.")

    async def lookup_program_docs(query: str) -> str:
        """Look up official program documentation to ground eligibility assessment.

        Pass a specific eligibility question or keyword phrase as *query* (e.g.
        "income limits household size", "in-home care requirements", "veteran
        service-connected disability").  Returns up to 5 relevant passages from
        official program documentation with title and page citations.
        """
        from app.rag.index import get_index  # deferred: index is shared singleton

        try:
            index = get_index()
            hits = index.search(query, k=_DEFAULT_K, scope=scope)
        except Exception:
            logger.exception(
                "RAG retrieval failed for doc_key=%s query=%r", doc_key, query
            )
            raise RuntimeError("Scoped policy retrieval unavailable; assessment must not proceed without evidence.") from None

        if not hits:
            return (
                f"[No results for '{query}' in {doc_key} corpus] "
                "No applicable passages found for the supplied jurisdiction/date. "
                "This is a coverage gap, not evidence of ineligibility; keep the conclusion unresolved."
            )

        parts: list[str] = []
        for i, h in enumerate(hits, start=1):
            citation = h.title or h.source or doc_key
            if h.page:
                citation = f"{citation} (p. {h.page})"
            parts.append(f"[{i}] {citation} — {h.document_id or h.source}\n"
                         f"Policy metadata: {json.dumps(h.policy)}\n{h.text.strip()}")

        return "\n\n".join(parts)

    return lookup_program_docs
