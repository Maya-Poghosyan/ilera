from fastapi import APIRouter
from fastapi.responses import Response

from .. import db
from ..config import get_settings
from ..rag.embeddings import provider as embedding_provider
from ..rag.index import get_index

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict:
    """Liveness only — cheap enough for a platform health check."""
    return {"status": "ok"}


@router.get("/readyz")
def readyz(response: Response) -> dict:
    """Readiness: can this replica actually serve requests?

    Separate from /healthz because the answers differ. A replica whose DATABASE_URL is wrong
    accepts connections and passes liveness, but every case it is handed is lost, so it must
    not receive traffic — answering 503 here keeps the previous good revision serving instead.
    Costs one SELECT 1, so it is cheap enough to poll every few seconds.
    """
    postgres = db.ready()
    if postgres is False:
        response.status_code = 503
    return {"status": "ok" if postgres is not False else "unavailable", "postgres": postgres}


@router.get("/health")
def health() -> dict:
    """Configuration report, including whether RAG can actually serve.

    Attaches to the index rather than waiting for the first query to do it, so a store that is
    unreachable or was never ingested shows up here instead of as silently empty retrieval.
    Attaching costs a count query; nothing here can build an index.
    """
    index = get_index()
    return {
        "status": "ok",
        "postgres": db.ready(),
        "llm": get_settings().has_llm,

        "embeddings": embedding_provider(),
        "rag_ready": index.size > 0,
        "rag_backend": index.backend,
        "rag_chunks": index.size,
    }
