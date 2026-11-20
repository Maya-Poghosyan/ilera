"""HTTP boundary: spend limit, bounded body read, validation, and error mapping."""

import time
from collections import deque

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from .extractor import read_document
from .models import HTTP_STATUS, DocumentError, DocumentReading, ErrorCode
from .upload import MAX_BYTES, Upload

router = APIRouter()


class SpendLimit:
    """Model calls allowed per window on this replica.

    Intake is anonymous and requests arrive through the web proxy, so there is no trustworthy
    per-person key; this bounds total cost instead."""

    def __init__(self, limit: int, window_s: float):
        self.limit, self.window = limit, window_s
        self._calls: deque[float] = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self._calls and now - self._calls[0] > self.window:
            self._calls.popleft()
        if len(self._calls) >= self.limit:
            return False
        self._calls.append(now)
        return True


spend_limit = SpendLimit(limit=300, window_s=3600)


async def _read_body(request: Request) -> bytes:
    if int(request.headers.get("content-length") or 0) > MAX_BYTES:
        raise DocumentError(ErrorCode.TOO_LARGE)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise DocumentError(ErrorCode.TOO_LARGE)
    return bytes(data)


@router.post("/api/intake/documents", response_model=DocumentReading)
async def read_intake_document(request: Request) -> DocumentReading:
    """Read one document (the raw request body) in memory and return answer suggestions to review.

    Nothing is stored or logged."""
    try:
        upload = Upload.parse(await _read_body(request))
        if not spend_limit.allow():
            raise DocumentError(ErrorCode.RATE_LIMITED)
        return await run_in_threadpool(read_document, upload)
    except DocumentError as err:
        raise HTTPException(HTTP_STATUS[err.code], err.code.value) from None
