"""Azure Service Bus publisher. Invoke only after validating the provider notification.

Broker duplicate detection is an optimization, not worker idempotency. The worker must
also atomically persist its processing result and extracted events before acknowledging.
"""

from .models import EmailScanJob
from ..config import get_settings


def enqueue_scan(job: EmailScanJob) -> None:
    settings = get_settings()
    if not settings.email_scanning_enabled:
        raise RuntimeError("Email scanning is disabled")
    if not settings.email_service_bus_namespace:
        raise RuntimeError("EMAIL_SERVICE_BUS_NAMESPACE is required")
    if not settings.has_postgres:
        raise RuntimeError("Email ingestion requires Postgres")

    # Lazy imports keep the ordinary API bootable before email dependencies are installed.
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    from azure.servicebus import ServiceBusClient, ServiceBusMessage

    credential = (
        ManagedIdentityCredential(client_id=settings.email_managed_identity_client_id or None)
        if settings.email_use_managed_identity
        else DefaultAzureCredential()
    )
    with credential:
        with ServiceBusClient(
            fully_qualified_namespace=settings.email_service_bus_namespace,
            credential=credential,
            logging_enable=False,
        ) as client:
            with client.get_queue_sender(settings.email_service_bus_queue) as sender:
                sender.send_messages(ServiceBusMessage(
                    job.model_dump_json(),
                    content_type="application/json",
                    message_id=job.deduplication_id,
                    subject="email.scan.v1",
                ))
