"""Launch the real API for the browser tests, replacing only the external services.

- the document model client → the local fake (frontend/e2e/fake-azure-openai.mjs)
- the PDF parse time limit → 2 seconds
- outgoing email (ACS) → captured, readable at GET /__e2e/mail/{address}
- the Azure Functions eligibility pipeline → not started (cases stay "processing";
  POST /__e2e/cases/{id}/eligible/{program} records one program's result)

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
# Every setting the API requires at startup; external services are replaced below, so these
# only need to be well-formed.
os.environ.update(
    JWT_SECRET="e2e-secret", CORS_ORIGINS="http://127.0.0.1", OPENAI_API_KEY="e2e",
    OPENAI_BASE_URL="https://e2e.openai.azure.com/openai/v1", AZURE_FUNCTIONS_URL="https://e2e.azurewebsites.net",
    AZURE_FUNCTIONS_KEY="e2e", ACS_EMAIL_CONNECTION_STRING="endpoint=https://e2e/;accesskey=e2e",
    EMAIL_MICROSOFT_TENANT_ID="00000000-0000-0000-0000-000000000001",
    EMAIL_MICROSOFT_CLIENT_ID="00000000-0000-0000-0000-000000000002",
    EMAIL_MICROSOFT_REDIRECT_URI="https://e2e.test/api/email/microsoft/callback",
    EMAIL_MICROSOFT_NOTIFICATION_URL="https://e2e.test/api/email/microsoft/notifications",
    EMAIL_KEY_VAULT_URL="https://e2e.vault.azure.net", EMAIL_SERVICE_BUS_NAMESPACE="e2e.servicebus.windows.net",
    DOCUMENT_OPENAI_ENDPOINT="https://e2e.openai.azure.com", DOCUMENT_OPENAI_DEPLOYMENT="e2e-documents",
    REFERENCE_GUIDES_BLOB_ACCOUNT_URL="https://e2e.blob.core.windows.net",
)

from app.accounts import mail as account_mail  # noqa: E402
from app.cases import pipeline  # noqa: E402
from app.intake.documents import extractor, upload  # noqa: E402
from app.main import app  # noqa: E402
from tests.intake_helpers import complete_current_intake  # noqa: E402


def fake_client(stack, *, endpoint, managed_identity_client_id="", timeout=45):
    return stack.enter_context(OpenAI(base_url=f"http://127.0.0.1:{model_port}/openai/v1/", api_key="e2e", timeout=timeout))


async def no_pipeline(profile):
    return f"eligibility-{profile.id}"


outbox: dict[str, list[dict]] = defaultdict(list)
extractor.open_client = fake_client
# A short PDF time limit, so the spec's slow-but-valid PDF hits it in seconds.
upload.PDF_TIMEOUT_S = 2
pipeline.start_eligibility_orchestration = no_pipeline
account_mail.send_verification_link = lambda email, token: outbox[email.lower()].append({"kind": "verify", "token": token})
account_mail.send_login_code = lambda email, code: outbox[email.lower()].append({"kind": "otp", "code": code})

e2e = APIRouter(prefix="/__e2e")
e2e.add_api_route("/mail/{address}", lambda address: outbox[address.lower()], methods=["GET"])
e2e.add_api_route("/complete-intake", lambda: complete_current_intake(), methods=["GET"])


def mark_eligible(case_id: str, program: str):
    """Stand in for the eligibility pipeline's result for one program."""
    from app.cases import store
    from app.cases.models import EligibilityResult
    profile = store.get_profile(case_id)
    profile.eligibility[program] = EligibilityResult(program=program, confidence=0.8, status="likely",
                                                     rationale="Marked eligible for the browser test.")
    store.save_profile(profile)
    return {"ok": True}


e2e.add_api_route("/cases/{case_id}/eligible/{program}", mark_eligible, methods=["POST"])
app.include_router(e2e)

uvicorn.run(app, host="127.0.0.1", port=api_port)
