"""Verify the Band connection using the 'routing' agent from the registry file.

Run from backend/:  python scripts/band_verify.py
Requires band_agents.json (with a 'routing' entry) and OPENAI_API_KEY
(BAND_WS_URL/BAND_REST_URL and OPENAI_BASE_URL / OPENAI_MODEL optional).
"""

import asyncio
import os

from band import Agent
from band.adapters.pydantic_ai import PydanticAIAdapter
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.integrations.band import load_registry


async def main() -> None:
    registry = load_registry()
    routing = registry.get("routing")
    if not routing:
        raise SystemExit("No 'routing' agent found in band_agents.json")
    agent_id = routing["agent_id"]
    api_key = routing["api_key"]
    ws_url = os.getenv("BAND_WS_URL", "wss://app.band.ai/api/v1/socket/websocket")
    rest_url = os.getenv("BAND_REST_URL", "https://app.band.ai")

    client = AsyncOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL") or None,
    )
    model = OpenAIChatModel(
        os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        provider=OpenAIProvider(openai_client=client),
    )
    adapter = PydanticAIAdapter(
        model=model,
        custom_section="You are the Ilera routing agent for caregiver benefits.",
    )
    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=ws_url,
        rest_url=rest_url.rstrip("/"),
    )
    await agent.start()
    print(f"Connected as: {agent.agent_name!r} (running={agent.is_running})")
    await agent.stop()
    print("Setup verified successfully.")


if __name__ == "__main__":
    asyncio.run(main())
