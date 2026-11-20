"""Launch the API for the browser tests with the document model swapped for the local fake.

Production code has exactly one way to reach the model (managed identity to the dedicated
Azure resource); this test entry point replaces that one client and nothing else.
Usage: python tests/e2e_api.py <api_port> <fake_model_port>
"""
import os
import sys
from pathlib import Path

import uvicorn
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
api_port, model_port = int(sys.argv[1]), int(sys.argv[2])
os.environ.update(DOCUMENT_OPENAI_ENDPOINT="https://e2e.openai.azure.com", DOCUMENT_OPENAI_DEPLOYMENT="e2e-documents")

from app.intake.documents import extractor  # noqa: E402
from app.main import app  # noqa: E402


def fake_client(stack, *, endpoint, managed_identity_client_id="", timeout=45):
    return stack.enter_context(OpenAI(base_url=f"http://127.0.0.1:{model_port}/openai/v1/", api_key="e2e", timeout=timeout))


extractor.open_client = fake_client
uvicorn.run(app, host="127.0.0.1", port=api_port)
