"""Tests run against a real Postgres (with pgvector) and never inherit a developer's .env.

Start one with:  docker run -d --name ilera-test-pg -e POSTGRES_PASSWORD=ilera \
  -e POSTGRES_DB=ilera_test -p 55432:5432 pgvector/pgvector:pg16
and export TEST_DATABASE_URL=postgresql://postgres:ilera@127.0.0.1:55432/ilera_test
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if not os.environ.get("TEST_DATABASE_URL"):
    raise RuntimeError("TEST_DATABASE_URL is required; see tests/conftest.py")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.config import Settings, get_settings  # noqa: E402

Settings.model_config["env_file"] = None
get_settings.cache_clear()


import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(autouse=True)
def orchestrator(monkeypatch):
    """The Azure Functions pipeline is the one external call intake makes; record it instead."""
    import durable.client

    started = []

    async def start(profile):
        started.append(profile.id)
        return f"eligibility-{profile.id}"

    monkeypatch.setattr(durable.client, "start_eligibility_orchestration", start)
    return started


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)
