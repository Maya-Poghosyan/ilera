"""Fixed email-route errors and transport log suppression for mailbox operations."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

_private_transport = ContextVar("email_private_transport", default=False)


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


def private_transport(function):
    @wraps(function)
    async def wrapped(*args, **kwargs):
        # Import before enumerating: httpcore registers its per-module loggers on import.
        import httpcore  # noqa: F401

        with private_transport_logs():
            return await function(*args, **kwargs)
    return wrapped


class EmailAccessLogFilter(logging.Filter):
    def filter(self, record):
        # Uvicorn's access record: client, method, full path, version, status.
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, path, version, status = record.args
            if isinstance(path, str) and path.split("?", 1)[0].startswith("/api/email/"):
                record.args = (client, method, "/api/email/[redacted]", version, status)
        return True


def configure_email_access_logging():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, EmailAccessLogFilter) for f in logger.filters):
        logger.addFilter(EmailAccessLogFilter())


class PrivateEmailRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_handler(request: Request):
            try:
                response = await handler(request)
            except RequestValidationError:
                # FastAPI's default detail includes `input`, even for SecretStr fields.
                response = JSONResponse({"detail": "Invalid email request"}, status_code=422)
            except HTTPException as exc:
                # Explicit route/auth errors contain fixed, developer-controlled messages.
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                                        headers=exc.headers)
            except Exception:
                # DB/SDK exceptions may include SQL parameters, tokens, or mailbox data.
                # Do not let the ASGI server emit an exception traceback with that data.
                response = JSONResponse({"detail": "Email service temporarily unavailable"}, status_code=503)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response

        return private_handler
