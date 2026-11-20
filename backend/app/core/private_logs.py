"""Suppress transport-SDK logging while private data (mail, uploaded documents) is in flight."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

_private_transport = ContextVar("private_transport", default=False)


class _TransportFilter(logging.Filter):
    def filter(self, record):
        return not _private_transport.get()


_transport_filter = _TransportFilter()


@contextmanager
def private_transport_logs():
    # Call after importing transport SDKs so their leaf loggers are registered.
    for name in ["httpx", "httpcore", "azure", "openai", *list(logging.Logger.manager.loggerDict)]:
        if name in {"httpx", "httpcore", "azure", "openai"} or name.startswith(("httpcore.", "azure.", "openai.")):
            logging.getLogger(name).addFilter(_transport_filter)
    token = _private_transport.set(True)
    try:
        yield
    finally:
        _private_transport.reset(token)
