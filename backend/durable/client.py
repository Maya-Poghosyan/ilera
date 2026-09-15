"""FastAPI → Azure Durable Functions HTTP bridge.

Provides two async helpers used by the FastAPI application layer to:
  1. Trigger the eligibility orchestration for a case profile.
  2. Poll the orchestration status (for server-sent-event or polling endpoints).

Both helpers read the Function App URL and optional function key from Settings.
They do NOT depend on the azure-durable-functions SDK — they call the standard
Durable HTTP management API via httpx, keeping the FastAPI container free of the
Functions runtime.
"""

from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.models import CaseProfile
from durable.models import CaseInput

logger = logging.getLogger(__name__)


async def start_eligibility_orchestration(profile: CaseProfile) -> str:
    """POST to the Function App's HTTP starter and return the Durable instance ID.

    The instance ID is deterministic (`eligibility-{profile.id}`) so duplicate calls
    are idempotent — the Durable runtime returns the existing instance.

    Args:
        profile: The CaseProfile to assess.

    Returns:
        The Durable instance ID (typically ``eligibility-{case_id}``).

    Raises:
        httpx.HTTPStatusError: Non-2xx response from the Function App.
        httpx.TimeoutException: Function App did not respond within the timeout.
    """
    s = get_settings()
    base_url = (s.azure_functions_url or "").rstrip("/")
    url = f"{base_url}/api/eligibility/{profile.id}"
    headers: dict[str, str] = {}
    if getattr(s, "azure_functions_key", ""):
        headers["x-functions-key"] = s.azure_functions_key

    payload = CaseInput(
        case_id=profile.id,
        profile_json=profile.model_dump_json(),
    ).model_dump()

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()

    data = resp.json()
    # The HTTP starter returns a check-status object; extract the id field if present.
    instance_id: str = data.get("id", f"eligibility-{profile.id}")
    logger.info(
        "start_eligibility_orchestration: started instance_id=%s for case_id=%s",
        instance_id,
        profile.id,
    )
    return instance_id


async def get_orchestration_status(instance_id: str) -> dict:
    """Poll the Durable management API for the given instance's status.

    Args:
        instance_id: The Durable orchestration instance ID.

    Returns:
        The raw status dict from the Durable management API.  Key fields:
          runtimeStatus  — "Pending", "Running", "Completed", "Failed", "Terminated"
          output         — the orchestrator's return value when Completed
          customStatus   — any custom status the orchestrator set

    Raises:
        httpx.HTTPStatusError: Non-2xx response.
        httpx.TimeoutException: Management endpoint timed out.
    """
    s = get_settings()
    base_url = (s.azure_functions_url or "").rstrip("/")
    url = (
        f"{base_url}/runtime/webhooks/durabletask/instances/{instance_id}"
    )
    headers: dict[str, str] = {}
    if getattr(s, "azure_functions_key", ""):
        headers["x-functions-key"] = s.azure_functions_key

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()

    return resp.json()
