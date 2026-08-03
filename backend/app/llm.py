"""LLM access (OpenAI / Azure OpenAI). Returns structured JSON for agent reasoning.

`available()` lets callers fall back to heuristics when no key is configured.
OpenAI supports an OpenAI-compatible `OPENAI_BASE_URL` (e.g. an Azure OpenAI v1 endpoint).
"""

import json
from typing import Any

from .config import get_settings


def available() -> bool:
    return bool(get_settings().openai_api_key)


def complete_json(system: str, user: str, max_tokens: int = 1024) -> dict[str, Any]:
    """Ask the LLM for a single JSON object and parse it. Raises if unavailable."""
    if not get_settings().openai_api_key:
        raise RuntimeError("No OpenAI API key configured")
    text = _openai(system, user, max_tokens)
    return _parse_json(text)


def _openai(system: str, user: str, max_tokens: int) -> str:
    from openai import OpenAI

    s = get_settings()
    client = OpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url or None)
    # `max_completion_tokens` is the current parameter and is required by reasoning
    # models (e.g. gpt-5*) which reject `max_tokens`. Reasoning tokens count against
    # the budget, so keep it generous enough to leave room for the JSON output.
    resp = client.chat.completions.create(
        model=s.openai_model,
        max_completion_tokens=max(max_tokens, 4096),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or "{}"


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)
