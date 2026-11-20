"""QA: configuration is validated at startup, not discovered on a request."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings


def test_bad_formats_are_rejected_when_settings_load():
    for bad in ({"email_key_vault_url": "https://evil.example.com"},
                {"email_microsoft_tenant_id": "9188040d-6c67-4c5b-b112-36a304b66dad"},  # consumer tenant
                {"document_openai_endpoint": "https://x.openai.azure.com/openai/v1"},
                {"email_microsoft_notification_url": "https://ileracare.app/api/email/microsoft/notifications?x=1"}):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **bad)


def test_the_api_refuses_to_start_without_its_settings_and_names_them(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    get_settings.cache_clear()
    from app.main import app
    with pytest.raises(RuntimeError, match="api is missing required settings: .*JWT_SECRET"):
        with TestClient(app):
            pass
    get_settings.cache_clear()
