"""The uploaded file, validated once at the boundary, and the model input built from it."""

import base64
import json
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.intake.schema import DOCUMENT_UPLOAD
from app.intake.documents.models import DocumentError, ErrorCode

MAX_BYTES: int = DOCUMENT_UPLOAD["max_bytes"]
MAX_PDF_PAGES: int = DOCUMENT_UPLOAD["max_pdf_pages"]
MAX_TEXT_CHARS = 40_000
# A PDF is parsed in a child process (pdf_process.py) that is killed after this long. Real
# documents parse in well under a second.
PDF_TIMEOUT_S = 10
# At most this many parses run at once on a replica, each capped at pdf_process.MAX_MEMORY_BYTES.
_PDF_SLOTS = threading.BoundedSemaphore(2)
_PDF_PROCESS = str(Path(__file__).with_name("pdf_process.py"))

_SIGNATURES = {b"%PDF-": "pdf", b"\xff\xd8\xff": "jpeg", b"\x89PNG\r\n\x1a\n": "png"}


@dataclass(frozen=True)
class Upload:
    """A non-empty PDF, JPEG or PNG within the size limit. Only `parse` constructs one."""
    kind: Literal["pdf", "jpeg", "png"]
    data: bytes

    @classmethod
    def parse(cls, data: bytes) -> "Upload":
        if not data:
            raise DocumentError(ErrorCode.EMPTY)
        if len(data) > MAX_BYTES:
            raise DocumentError(ErrorCode.TOO_LARGE)
        kind = next((k for sig, k in _SIGNATURES.items() if data.startswith(sig)), None)
        if kind is None:
            raise DocumentError(ErrorCode.UNSUPPORTED_TYPE)
        return cls(kind, data)


@dataclass(frozen=True)
class ModelInput:
    content: list[dict]
    pages: int


def model_input(upload: Upload) -> ModelInput:
    if upload.kind == "pdf":
        text, pages = _pdf_text(upload.data)
        return ModelInput([{"type": "text", "text": "Document text (untrusted):\n" + text}], pages)
    url = f"data:image/{upload.kind};base64,{base64.b64encode(upload.data).decode()}"
    return ModelInput([{"type": "text", "text": "Document image (untrusted) follows."},
                       {"type": "image_url", "image_url": {"url": url, "detail": "high"}}], 1)


def _pdf_text(data: bytes) -> tuple[str, int]:
    if not _PDF_SLOTS.acquire(timeout=PDF_TIMEOUT_S):
        raise DocumentError(ErrorCode.RATE_LIMITED)
    try:
        done = subprocess.run([sys.executable, "-I", _PDF_PROCESS, str(MAX_PDF_PAGES)], input=data,
                              capture_output=True, timeout=PDF_TIMEOUT_S)
        result = json.loads(done.stdout) if done.returncode == 0 else {"error": "unreadable"}
    except (subprocess.TimeoutExpired, ValueError):
        # A parse that runs out of time or memory reads as an unreadable file.
        raise DocumentError(ErrorCode.UNREADABLE) from None
    finally:
        _PDF_SLOTS.release()
    if "error" in result:
        raise DocumentError(ErrorCode(result["error"]))
    texts: list[str] = result["pages"]
    if sum(c.isalnum() for t in texts for c in t) < 20:
        # Scanned PDFs have no text layer; a photo of the page works instead.
        raise DocumentError(ErrorCode.NO_TEXT_LAYER)
    text = "\n\n".join(f"[Page {i}]\n{t}" for i, t in enumerate(texts, 1))
    return text[:MAX_TEXT_CHARS], len(texts)
