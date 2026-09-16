import asyncio
import logging

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr, ValidationError

from app.email_ingestion.models import EmailMessage
from app.email_ingestion.privacy import EmailAccessLogFilter, PrivateEmailRoute, private_transport, private_transport_logs


class Callback(BaseModel):
    state: SecretStr


def test_invalid_input_and_unexpected_exceptions_are_not_disclosed(caplog):
    app = FastAPI()
    router = APIRouter(route_class=PrivateEmailRoute)

    @router.post('/callback')
    def callback(body: Callback):
        raise RuntimeError('PHI-SENTINEL database values')

    app.include_router(router)
    client = TestClient(app)
    for payload, status in [({'state': {'PHI-SENTINEL': 'secret'}}, 422), ({'state': 'valid'}, 503)]:
        response = client.post('/callback', json=payload)
        assert response.status_code == status
        assert 'PHI-SENTINEL' not in response.text
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['referrer-policy'] == 'no-referrer'
    assert 'PHI-SENTINEL' not in caplog.text


def test_validation_exception_does_not_print_message_content():
    try:
        EmailMessage(message_id='m', received_at='PHI-SENTINEL', sender='s', subject='private', body_text='private')
    except ValidationError as exc:
        assert 'PHI-SENTINEL' not in str(exc)
    else:
        raise AssertionError('Expected invalid timestamp')


def test_access_log_redacts_queries_and_connection_ids():
    record = logging.LogRecord('uvicorn.access', logging.INFO, '', 1, '%s %s %s %s %s',
        ('client', 'GET', '/api/email/connections/PHI-SENTINEL?code=SECRET', '1.1', 200), None)
    assert EmailAccessLogFilter().filter(record)
    assert 'PHI-SENTINEL' not in record.getMessage()
    assert 'SECRET' not in record.getMessage()
    assert '200' in record.getMessage()


def test_mailbox_transport_logs_suppressed_and_context_restored(caplog):
    @private_transport
    async def operation():
        logging.getLogger('httpx').info('PHI-SENTINEL Graph message URL')
        logging.getLogger('httpcore.connection').debug('PHI-SENTINEL response')
        raise RuntimeError('fixed')

    with caplog.at_level(logging.DEBUG):
        try:
            asyncio.run(operation())
        except RuntimeError:
            pass
        logging.getLogger('httpx').info('ordinary-request')
    assert 'PHI-SENTINEL' not in caplog.text
    assert 'ordinary-request' in caplog.text


def test_azure_sdk_logs_suppressed_inside_private_scope(caplog):
    logger = logging.getLogger('azure.core.pipeline.policies.http_logging_policy')
    with caplog.at_level(logging.DEBUG):
        with private_transport_logs():
            logger.warning('PHI-SENTINEL response payload')
        logger.info('outside-private-operation')
    assert 'PHI-SENTINEL' not in caplog.text
    assert 'outside-private-operation' in caplog.text
