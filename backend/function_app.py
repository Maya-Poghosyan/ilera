"""Azure Functions entry point for the Ilera Durable eligibility pipeline.

This module registers all orchestrators, activities, and the HTTP starter with the
DFApp instance.  It lives at the backend root so that both `app/` and `durable/`
packages are importable without path manipulation.

Function registrations:
  Orchestrators:
    - eligibility_orchestrator   (main fan-out/fan-in pipeline)
    - peer_query_orchestrator    (cross-program sub-orchestration)
  Activities:
    - eligibility_gate           (fast deterministic gate checks)
    - specialist_activity        (LLM + RAG specialist assessment)
    - synthesis_activity         (DB persist + LLM strategy synthesis)
  HTTP starter:
    - http_start_eligibility     POST /api/eligibility/{case_id}
"""

from __future__ import annotations

import json

import azure.durable_functions as df
import azure.functions as func

# Import the raw generator / async functions — decorators are applied below.
from durable.activities.eligibility_gate import eligibility_gate
from durable.activities.specialist import specialist_activity
from durable.activities.synthesis import synthesis_activity
from durable.orchestrators.eligibility import eligibility_orchestrator
from durable.orchestrators.peer_query import peer_query_orchestrator

# DFApp is the v2 programming model app object for Durable Functions.
app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

# ── Register orchestrators ─────────────────────────────────────────────────────

app.orchestration_trigger(context_name="context")(eligibility_orchestrator)
app.orchestration_trigger(context_name="context")(peer_query_orchestrator)

# ── Register activities ────────────────────────────────────────────────────────

app.activity_trigger(input_name="payload")(eligibility_gate)
app.activity_trigger(input_name="payload")(specialist_activity)
app.activity_trigger(input_name="payload")(synthesis_activity)

# ── HTTP starter ───────────────────────────────────────────────────────────────


@app.route(route="eligibility/{case_id}", methods=["POST"])
@app.durable_client_input(client_name="client")
async def http_start_eligibility(
    req: func.HttpRequest,
    client: df.DurableOrchestrationClient,
) -> func.HttpResponse:
    """HTTP starter: POST /api/eligibility/{case_id}

    Request body (JSON):
        case_id      str  — case identifier (also available as route param)
        profile_json str  — JSON-serialised CaseProfile

    Returns a Durable check-status response with statusQueryGetUri, etc.

    The instance ID is deterministic (`eligibility-{case_id}`) so a duplicate
    POST is idempotent: the Durable runtime will return the existing instance's
    status rather than spawning a second orchestration.
    """
    case_id = req.route_params.get("case_id", "")

    try:
        body = json.loads(req.get_body() or b"{}")
    except json.JSONDecodeError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON"}),
            status_code=400,
            mimetype="application/json",
        )

    instance_id = f"eligibility-{case_id}"

    await client.start_new(
        "eligibility_orchestrator",
        instance_id=instance_id,
        client_input=body,
    )

    return client.create_check_status_response(req, instance_id)
