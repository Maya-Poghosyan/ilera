"""LLM access (Anthropic). Returns structured JSON for agent reasoning.

`available()` lets callers fall back to heuristics when no key is configured.
"""

import json
from typing import Any

from .config import get_settings


def available() -> bool:
    s = get_settings()
    return bool(s.anthropic_api_key or s.openai_api_key)


def complete_json(system: str, user: str, max_tokens: int = 1024) -> dict[str, Any]:
    """Ask the LLM for a single JSON object and parse it. Raises if unavailable."""
    s = get_settings()
    if s.anthropic_api_key:
        text = _anthropic(system, user, max_tokens)
    elif s.openai_api_key:
        text = _openai(system, user, max_tokens)
    else:
        raise RuntimeError("No LLM key configured")
    return _parse_json(text)


def _anthropic(system: str, user: str, max_tokens: int) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=get_settings().anthropic_api_key)
    msg = client.messages.create(
        model=get_settings().anthropic_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in msg.content if block.type == "text")


def _openai(system: str, user: str, max_tokens: int) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=get_settings().openai_api_key)
    resp = client.chat.completions.create(
        model=get_settings().openai_model,
        max_tokens=max_tokens,
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
