"""Readiness has to answer 503 while Postgres is unreachable, or the platform will happily
route traffic to a replica that can't keep a single case."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

client = TestClient(app)


def test_readyz_ok_when_postgres_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "ready", lambda: True)
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "postgres": True}


def test_readyz_unavailable_when_postgres_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "ready", lambda: False)
    res = client.get("/readyz")
    assert res.status_code == 503
    assert res.json()["postgres"] is False


def test_readyz_ok_without_postgres_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """In-memory mode (no DATABASE_URL) is a valid way to run, so it stays ready."""
    monkeypatch.setattr(db, "ready", lambda: None)
    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "postgres": None}
