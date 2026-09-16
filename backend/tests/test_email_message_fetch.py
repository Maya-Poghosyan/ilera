import asyncio
import httpx
import pytest
from pydantic import SecretStr
from app.providers import microsoft as m


def provider(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(m.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    return object.__new__(m.MicrosoftEmailProvider)


def test_fetch_uses_immutable_ids_text_only_no_attachments(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'id':'id/plus+', 'receivedDateTime':'2026-09-16T12:00:00Z',
            'sender':{'emailAddress':{'address':'sender'}}, 'subject':'subject',
            'body':{'contentType':'text','content':'body'}})
    message = asyncio.run(provider(monkeypatch,handler).fetch_message(SecretStr('token'),'id/plus+'))
    assert message.body_text.get_secret_value() == 'body'
    assert 'ImmutableId' in requests[0].headers['Prefer']
    assert 'attachments' not in str(requests[0].url)
    assert requests[0].url.params['$select'] == 'id,sender,subject,receivedDateTime,body'


def test_large_response_fails_with_fixed_error(monkeypatch):
    instance = provider(monkeypatch, lambda req: httpx.Response(200, content=b'x'*2_000_001))
    with pytest.raises(m.ProviderError, match='^Microsoft mailbox request failed$'):
        asyncio.run(instance.fetch_message(SecretStr('token'),'id'))


def test_graph_unauthorized_requires_reconnect(monkeypatch):
    instance = provider(monkeypatch, lambda req: httpx.Response(401, text='PHI-SENTINEL'))
    with pytest.raises(m.ReauthorizationRequired, match='^Microsoft sign-in is required$'):
        asyncio.run(instance.fetch_message(SecretStr('token'),'id'))
