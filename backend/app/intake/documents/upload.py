"""The uploaded file, validated once at the boundary, and the model input built from it."""

import base64
import io
from dataclasses import dataclass
from typing import Literal

from ..schema import DOCUMENT_UPLOAD
from .models import DocumentError, ErrorCode

MAX_BYTES: int = DOCUMENT_UPLOAD["max_bytes"]
MAX_PDF_PAGES: int = DOCUMENT_UPLOAD["max_pdf_pages"]
MAX_TEXT_CHARS = 40_000

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
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentError(ErrorCode.ENCRYPTED_PDF)
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentError(ErrorCode.TOO_MANY_PAGES)
        texts = [(page.extract_text() or "").strip() for page in reader.pages]
    except DocumentError:
        raise
    except Exception:
        raise DocumentError(ErrorCode.UNREADABLE) from None
    if sum(c.isalnum() for t in texts for c in t) < 20:
        # Scanned PDFs have no text layer; a photo of the page works instead.
        raise DocumentError(ErrorCode.NO_TEXT_LAYER)
    text = "\n\n".join(f"[Page {i}]\n{t}" for i, t in enumerate(texts, 1))
    return text[:MAX_TEXT_CHARS], len(texts)
