"""Verify the Band connection using credentials from the environment.

Run from backend/:  python scripts/band_verify.py
Requires BAND_API_KEY, BAND_AGENT_ID, ANTHROPIC_API_KEY (BAND_WS_URL/REST_URL optional).
"""

import asyncio
import os

from band import Agent
from band.adapters.anthropic import AnthropicAdapter


async def main() -> None:
    agent_id = os.environ["BAND_AGENT_ID"]
    api_key = os.environ["BAND_API_KEY"]
    ws_url = os.getenv("BAND_WS_URL", "wss://app.band.ai/api/v1/socket/websocket")
    rest_url = os.getenv("BAND_REST_URL", "https://app.band.ai")

    adapter = AnthropicAdapter(
        model="claude-sonnet-4-5-20250929",
        system_prompt="You are the Ilera routing agent for caregiver benefits.",
        provider_key=os.environ["ANTHROPIC_API_KEY"],
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
