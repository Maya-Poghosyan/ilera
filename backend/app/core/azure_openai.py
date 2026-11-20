"""Dedicated Azure OpenAI deployments for private data (email scanning, intake documents).

Each feature has its own resource and managed identity and never falls back to the general
OPENAI_API_KEY used for eligibility research."""

from contextlib import ExitStack
from typing import TypeVar
from urllib.parse import urlparse

from pydantic import BaseModel

from app.core.azure_identity import managed_identity
from app.core.private_logs import private_transport_logs

M = TypeVar("M", bound=BaseModel)


def is_dedicated_endpoint(url: str) -> bool:
    """A bare https://<resource>.openai.azure.com origin, nothing else."""
    u = urlparse(url)
    return bool(u.scheme == "https" and u.hostname and u.hostname.endswith(".openai.azure.com")
                and not u.username and not u.password and u.port in (None, 443)
                and u.path in ("", "/") and not u.query and not u.fragment)


def open_client(stack: ExitStack, *, endpoint: str, managed_identity_client_id: str = "", timeout: float = 45):
    from azure.identity import get_bearer_token_provider
    from openai import OpenAI

    credential = stack.enter_context(managed_identity(managed_identity_client_id))
    auth = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    return stack.enter_context(OpenAI(base_url=endpoint.rstrip("/") + "/openai/v1/", api_key=auth,
                                      timeout=timeout, max_retries=0))


def structured_completion(client, *, deployment: str, system: str, content, output: type[M], name: str,
                          max_tokens: int = 4000, max_chars: int = 20_000) -> M:
    """One stored-nothing, tool-free, schema-constrained completion. Raises ValueError on anything off."""
    with private_transport_logs():
        completion = client.chat.completions.create(
            model=deployment, store=False, max_completion_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
            response_format={"type": "json_schema", "json_schema": {
                "name": name, "strict": True, "schema": output.model_json_schema()}},
        )
    choice = completion.choices[0]
    if choice.finish_reason != "stop" or choice.message.refusal or not choice.message.content:
        raise ValueError("Incomplete completion")
    if len(choice.message.content) > max_chars:
        raise ValueError("Oversized completion")
    return output.model_validate_json(choice.message.content)
