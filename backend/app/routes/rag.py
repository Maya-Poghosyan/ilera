from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from ..rag.index import get_index
from ..rag.scope import RetrievalScope, normalize_state, today as policy_today

router = APIRouter()


class RagQuery(BaseModel):
    query: str
    program: str = Field(min_length=1)
    state: str = Field(pattern=r"^[A-Z]{2}$")
    as_of: date = Field(default_factory=policy_today)
    k: int = Field(default=4, ge=1, le=20)

    @field_validator("state")
    @classmethod
    def valid_policy_state(cls, value: str) -> str:
        return normalize_state(value)


@router.post("/api/rag/search")
def rag_search(q: RagQuery) -> dict:
    hits = get_index().search(q.query, k=q.k, scope=RetrievalScope(q.program, q.state, q.as_of))
    return {
        "results": [
            {
                "text": h.text,
                "program": h.program,
                "source": h.source,
                "title": h.title,
                "source_url": h.source_url,
                "document_id": h.document_id,
                "page": h.page,
                "score": round(h.score, 4),
                "policy": h.policy,
            }
            for h in hits
        ]
    }
