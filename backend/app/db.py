"""Postgres persistence for users and cases.

Postgres (the same database that backs the pgvector RAG index) is the store of record
for accounts and CaseProfiles. Without `DATABASE_URL` everything falls back to
in-memory dicts so the app still boots with no services, as elsewhere.

Profiles are kept as `jsonb` rather than exploded into columns: `CaseProfile` is a deep,
still-changing Pydantic tree that only ever gets read and written whole.
"""

import logging
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

from .config import get_settings

logger = logging.getLogger("ilera.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              text PRIMARY KEY,
    name            text NOT NULL,
    email           text NOT NULL UNIQUE,
    hashed_password text NOT NULL,
    case_id         text,
    created_at      text NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cases (
    id         text PRIMARY KEY,
    profile    jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- A Band specialist tool only knows the room it runs in, so it resolves the room back
-- to the owning case through here. Shared by the API and the Band worker process.
CREATE TABLE IF NOT EXISTS band_rooms (
    room_id text PRIMARY KEY,
    case_id text NOT NULL
);
"""

_pool = None
_pool_lock = threading.Lock()


def available() -> bool:
    return get_settings().has_postgres


def _get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            from psycopg_pool import ConnectionPool

            pool = ConnectionPool(
                get_settings().database_url, min_size=1, max_size=4, open=True, timeout=15
            )
            with pool.connection() as conn:
                conn.execute(_SCHEMA)
            _pool = pool
        return _pool


@contextmanager
def connection() -> Iterator["object"]:
    """A pooled connection with the schema already applied."""
    with _get_pool().connection() as conn:
        yield conn


def reset_pool() -> None:
    """Drop the cached pool (tests that repoint DATABASE_URL)."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
        _pool = None


def ready() -> Optional[bool]:
    """True/False when Postgres is configured, None when it isn't."""
    if not available():
        return None
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        logger.exception("Postgres is configured but unreachable")
        return False
