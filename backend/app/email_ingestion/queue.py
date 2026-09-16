"""Request-scoped Service Bus publisher; identifiers only, no raw email or credentials.

A publisher is used in one worker thread, never shared between concurrent requests.
Broker deduplication does not replace atomic worker idempotency.
"""

from contextlib import ExitStack

from .models import EmailScanJob
from .privacy import private_transport_logs
from ..config import get_settings


class ScanPublisher:
    def __init__(self):
        self._stack = ExitStack()
        self._sender = None
        self._sent = set()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self._stack.__exit__(*args)

    def send(self, job: EmailScanJob) -> None:
        if job.deduplication_id in self._sent:
            return
        # Lazy: forged notifications/lifecycle-only batches never open Azure connections.
        from azure.servicebus import ServiceBusMessage

        if self._sender is None:
            settings = get_settings()
            if not (settings.email_scanning_enabled and settings.has_postgres
                    and settings.email_service_bus_namespace):
                raise RuntimeError("Email queue is unavailable")
            from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
            from azure.servicebus import ServiceBusClient

            self._stack.enter_context(private_transport_logs())
            credential = self._stack.enter_context(
                ManagedIdentityCredential(client_id=settings.email_managed_identity_client_id or None)
                if settings.email_use_managed_identity else DefaultAzureCredential()
            )
            client = self._stack.enter_context(ServiceBusClient(
                fully_qualified_namespace=settings.email_service_bus_namespace,
                credential=credential, logging_enable=False, retry_total=0,
            ))
            self._sender = self._stack.enter_context(client.get_queue_sender(settings.email_service_bus_queue))
        self._sender.send_messages(ServiceBusMessage(
            job.model_dump_json(), content_type="application/json",
            message_id=job.deduplication_id, subject="email.scan.v1",
        ), timeout=5)
        self._sent.add(job.deduplication_id)


def enqueue_scan(job: EmailScanJob) -> None:
    with ScanPublisher() as publisher:
        publisher.send(job)
