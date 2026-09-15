"""RAG tool factory for pydantic-ai specialist agents.

`make_rag_tool(doc_key)` returns an async function suitable for use as a pydantic-ai
tool.  Each returned function is scoped to its program's corpus slice, so the IHSS
specialist only retrieves IHSS documents, the VA specialist only VA documents, etc.

The function formats retrieved passages into a single string with inline citations
(title + page) that the LLM can reference in its structured output.

Error handling: RAG errors are caught here and an empty-but-informative string is
returned.  The specialist activity treats zero retrieved passages as a degraded path
but still proceeds with heuristic context — it does NOT raise from the tool.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Maximum number of passages to retrieve per query.
_DEFAULT_K = 5


def make_rag_tool(doc_key: str) -> Callable[..., str]:
    """Return a pydantic-ai-compatible async tool function scoped to *doc_key*.

    The returned coroutine's docstring is used by pydantic-ai as the tool description
    presented to the model, so it is intentionally in plain English.
    """

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
            hits = index.search(query, k=_DEFAULT_K, program=doc_key)
        except Exception:
            logger.exception(
                "RAG retrieval failed for doc_key=%s query=%r", doc_key, query
            )
            return (
                f"[RAG unavailable for {doc_key}] "
                "No documentation could be retrieved; base your assessment on general "
                "program knowledge and mark confidence accordingly."
            )

        if not hits:
            return (
                f"[No results for '{query}' in {doc_key} corpus] "
                "No matching passages found; the corpus may not cover this topic."
            )

        parts: list[str] = []
        for i, h in enumerate(hits, start=1):
            citation = h.title or h.source or doc_key
            if h.page:
                citation = f"{citation} (p. {h.page})"
            parts.append(f"[{i}] {citation}\n{h.text.strip()}")

        return "\n\n".join(parts)

    return lookup_program_docs
