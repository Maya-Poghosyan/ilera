import sys
from types import SimpleNamespace

import pytest

from app.email_ingestion import queue
from app.email_ingestion.models import EmailScanJob


@pytest.fixture
def sdk(monkeypatch):
    state = SimpleNamespace(credentials=0, clients=0, sends=[], closed=0, fail=False)

    class Resource:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            state.closed += 1

    class Credential(Resource):
        def __init__(self, **kw):
            state.credentials += 1

    class Sender(Resource):
        def send_messages(self, message, **kw):
            assert kw['timeout'] == 5
            if state.fail:
                raise RuntimeError('send failed')
            state.sends.append(message)

    class Client(Resource):
        def __init__(self, **kw):
            state.clients += 1
            assert kw['logging_enable'] is False
            assert kw['retry_total'] == 0
        def get_queue_sender(self, name):
            return Sender()

    monkeypatch.setitem(sys.modules, 'azure', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'azure.identity', SimpleNamespace(
        ManagedIdentityCredential=Credential, DefaultAzureCredential=Credential))
    monkeypatch.setitem(sys.modules, 'azure.servicebus', SimpleNamespace(
        ServiceBusClient=Client, ServiceBusMessage=lambda body, **kw: {'body': body, **kw}))
    monkeypatch.setattr(queue, 'get_settings', lambda: SimpleNamespace(
        email_scanning_enabled=True, has_postgres=True, email_service_bus_namespace='bus',
        email_use_managed_identity=True, email_managed_identity_client_id='', email_service_bus_queue='email.scan'))
    return state


def job(message='one'):
    return EmailScanJob(provider='microsoft', connection_id='connection', message_id=message)


def test_publisher_reuses_connection_and_skips_duplicates(sdk):
    with queue.ScanPublisher() as publisher:
        publisher.send(job())
        publisher.send(job())
        publisher.send(job('two'))
    assert sdk.credentials == sdk.clients == 1
    assert len(sdk.sends) == 2
    assert sdk.closed == 3


def test_unused_publisher_has_no_connections(sdk):
    with queue.ScanPublisher():
        pass
    assert sdk.credentials == sdk.clients == 0


def test_send_failure_is_not_marked_complete_and_resources_close(sdk):
    with queue.ScanPublisher() as publisher:
        sdk.fail = True
        with pytest.raises(RuntimeError):
            publisher.send(job())
        sdk.fail = False
        publisher.send(job())
    assert len(sdk.sends) == 1
    assert sdk.closed == 3
