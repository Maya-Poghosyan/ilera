"""Reads an uploaded PDF's text in a child process, so a hostile file costs one killed process.

- The parent (upload.py) runs this file with `python -I`, the PDF on stdin and the page limit
  as the only argument, and kills it after a time limit
- It caps its own memory, then prints one JSON object: {"pages": [...]} or {"error": "<code>"}
- It imports only pypdf, so it starts in a fraction of a second
"""

import io
import json
import sys

MAX_MEMORY_BYTES = 768 * 1024 * 1024


def _cap_memory() -> None:
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES))
    except (ImportError, ValueError, OSError):
        pass  # macOS ignores RLIMIT_AS; production (Linux) applies it


def read(data: bytes, max_pages: int) -> dict:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return {"error": "encrypted_pdf"}
        if len(reader.pages) > max_pages:
            return {"error": "too_many_pages"}
        return {"pages": [(page.extract_text() or "").strip() for page in reader.pages]}
    except Exception:
        return {"error": "unreadable"}


if __name__ == "__main__":
    _cap_memory()
    sys.stdout.write(json.dumps(read(sys.stdin.buffer.read(), int(sys.argv[1]))))
