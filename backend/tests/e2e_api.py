"""Launch the real API for the browser tests, replacing only the external services.

- the document model client → the local fake (frontend/e2e/fake-azure-openai.mjs)
- outgoing email (ACS) → captured, readable at GET /__e2e/mail/{address}
- the Azure Functions eligibility pipeline → not started (cases stay "processing")

Also serves GET /__e2e/complete-intake: a valid, complete set of intake answers, built by the
same helper the API tests use, so browser tests don't hand-maintain one.
Usage: python tests/e2e_api.py <api_port> <fake_model_port>
"""
import os
import sys
from collections import defaultdict
from pathlib import Path

import uvicorn
from fastapi import APIRouter
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
api_port, model_port = int(sys.argv[1]), int(sys.argv[2])
os.environ.update(DOCUMENT_OPENAI_ENDPOINT="https://e2e.openai.azure.com", DOCUMENT_OPENAI_DEPLOYMENT="e2e-documents",
                  JWT_SECRET=os.environ.get("JWT_SECRET") or "e2e-secret")

import durable.client  # noqa: E402
from app import auth  # noqa: E402
from app.intake.documents import extractor  # noqa: E402
from app.main import app  # noqa: E402
from tests.intake_helpers import complete_current_intake  # noqa: E402


def fake_client(stack, *, endpoint, managed_identity_client_id="", timeout=45):
    return stack.enter_context(OpenAI(base_url=f"http://127.0.0.1:{model_port}/openai/v1/", api_key="e2e", timeout=timeout))


async def no_pipeline(profile):
    return f"eligibility-{profile.id}"


mail: dict[str, list[dict]] = defaultdict(list)
extractor.open_client = fake_client
durable.client.start_eligibility_orchestration = no_pipeline
auth._send_verification_email = lambda email, token: mail[email.lower()].append({"kind": "verify", "token": token})
auth._send_otp_email = lambda email, code: mail[email.lower()].append({"kind": "otp", "code": code})

e2e = APIRouter(prefix="/__e2e")
e2e.add_api_route("/mail/{address}", lambda address: mail[address.lower()], methods=["GET"])
e2e.add_api_route("/complete-intake", lambda: complete_current_intake(), methods=["GET"])
app.include_router(e2e)

uvicorn.run(app, host="127.0.0.1", port=api_port)
