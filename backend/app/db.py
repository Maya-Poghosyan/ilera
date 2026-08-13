"""Postgres persistence for everything the app stores.

Postgres (the same database that backs the pgvector RAG index) is the store of record:
accounts, CaseProfiles, reminders, care records, application state, preferences, and
suggested events. Without `DATABASE_URL` every store falls back to an in-memory dict so
the app still boots with no services, as elsewhere.

Apart from `users`, rows keep the Pydantic model whole in a `doc jsonb` column rather than
exploding it into columns: these models are deep, still-changing trees that are only ever
read and written entirely. `JsonStore` is that shape, and it owns the in-memory fallback
so callers never branch on whether a database is configured.
"""

import json
import logging
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

from .config import get_settings

logger = logging.getLogger("ilera.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              text PRIMARY KEY,
    name            text NOT NULL,
    email           text NOT NULL UNIQUE,
    hashed_password text NOT NULL,
    created_at      text NOT NULL DEFAULT ''
);

-- owner_user_id is nullable because intake runs before there is an account: a case starts
-- unowned, reachable only by whoever holds its id, and is claimed at signup. The foreign key
-- makes an owner that isn't a real user impossible; ownership checks are enforced in access.py.
CREATE TABLE IF NOT EXISTS cases (
    id            text PRIMARY KEY,
    owner_user_id text REFERENCES users (id) ON DELETE CASCADE,
    doc           jsonb NOT NULL,
    updated_at    timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS owner_user_id text REFERENCES users (id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS cases_owner_idx ON cases (owner_user_id);

-- Ownership used to be a users.case_id pointer, which allowed two users to name the same case
-- and let a case outlive any claim to it. Adopt those pointers as ownership, then drop them so
-- cases.owner_user_id is the only answer to "whose case is this".
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'case_id'
    ) THEN
        UPDATE cases c SET owner_user_id = u.id
          FROM users u
         WHERE u.case_id = c.id AND c.owner_user_id IS NULL;
        ALTER TABLE users DROP COLUMN case_id;
    END IF;
END $$;

-- A Band specialist tool only knows the room it runs in, so it resolves the room back
-- to the owning case through here. Shared by the API and the Band worker process.
CREATE TABLE IF NOT EXISTS band_rooms (
    room_id text PRIMARY KEY,
    case_id text NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id         text PRIMARY KEY,
    doc        jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS timekeeping (
    id         text PRIMARY KEY,
    case_id    text NOT NULL,
    doc        jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS timekeeping_case_idx ON timekeeping (case_id);

CREATE TABLE IF NOT EXISTS journal (
    id         text PRIMARY KEY,
    case_id    text NOT NULL,
    doc        jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS journal_case_idx ON journal (case_id);

CREATE TABLE IF NOT EXISTS renewals (
    case_id    text PRIMARY KEY,
    doc        jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS applications (
    case_id    text NOT NULL,
    program    text NOT NULL,
    doc        jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, program)
);

CREATE TABLE IF NOT EXISTS preferences (
    case_id    text PRIMARY KEY,
    doc        jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS suggested_events (
    id         text PRIMARY KEY,
    doc        jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
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
def connection() -> Iterator[Any]:
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


class JsonStore:
    """A `(key columns…, doc jsonb)` table, with an in-memory twin for when there is no
    database. Values go in as the model's JSON and come back out as plain dicts.

    `case_id` is a real column (not just part of the document) wherever entries are listed
    per case, so listing is an indexed lookup instead of a scan-and-filter.
    """

    def __init__(
        self, table: str, keys: Sequence[str] = ("id",), scoped_by_case: bool = False
    ) -> None:
        self.table = table
        self.keys = tuple(keys)
        # A store keyed by case_id is already scoped by it.
        self.scoped_by_case = scoped_by_case and "case_id" not in self.keys
        self._memory: dict[tuple[str, ...], tuple[str, dict]] = {}

    def _columns(self) -> tuple[str, ...]:
        scope = ("case_id",) if self.scoped_by_case else ()
        return self.keys + scope + ("doc",)

    @staticmethod
    def _as_key(key: str | Sequence[str]) -> tuple[str, ...]:
        return (key,) if isinstance(key, str) else tuple(key)

    def _where(self) -> str:
        return " AND ".join(f"{k} = %s" for k in self.keys)

    def put(self, key: str | Sequence[str], payload: str, case_id: str = "") -> None:
        key = self._as_key(key)
        if not available():
            self._memory[key] = (case_id, json.loads(payload))
            return
        columns = self._columns()
        values = [*key, *((case_id,) if self.scoped_by_case else ()), payload]
        placeholders = ", ".join(["%s"] * (len(values) - 1) + ["%s::jsonb"])
        updates = ", ".join(
            [f"{c} = EXCLUDED.{c}" for c in columns if c not in self.keys] + ["updated_at = now()"]
        )
        with connection() as conn:
            conn.execute(
                f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders}) "  # noqa: S608
                f"ON CONFLICT ({', '.join(self.keys)}) DO UPDATE SET {updates}",
                values,
            )

    def get(self, key: str | Sequence[str]) -> Optional[dict]:
        key = self._as_key(key)
        if not available():
            found = self._memory.get(key)
            return found[1] if found else None
        with connection() as conn:
            row = conn.execute(
                f"SELECT doc FROM {self.table} WHERE {self._where()}", key  # noqa: S608
            ).fetchone()
        return row[0] if row else None

    def delete(self, key: str | Sequence[str]) -> bool:
        key = self._as_key(key)
        if not available():
            return self._memory.pop(key, None) is not None
        with connection() as conn:
            cur = conn.execute(
                f"DELETE FROM {self.table} WHERE {self._where()}", key  # noqa: S608
            )
            return cur.rowcount > 0

    def list(self, case_id: str = "") -> list[dict]:
        """Every document, or only a case's when `case_id` is given (requires a case
        column or a case key)."""
        column = "case_id" if self.scoped_by_case or "case_id" in self.keys else ""
        if not available():
            if not case_id:
                return [doc for _, doc in self._memory.values()]
            return [
                doc
                for (scope, doc) in self._memory.values()
                if scope == case_id or doc.get("case_id") == case_id
            ]
        sql = f"SELECT doc FROM {self.table}"  # noqa: S608
        params: tuple[str, ...] = ()
        if case_id and column:
            sql += f" WHERE {column} = %s"
            params = (case_id,)
        with connection() as conn:
            return [row[0] for row in conn.execute(sql, params).fetchall()]
