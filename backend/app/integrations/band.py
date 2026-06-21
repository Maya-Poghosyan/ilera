"""Band integration — runs Ilera's Routing Agent as a real Band participant.

The agent connects to the Band platform (https://docs.band.ai) over a websocket and
exposes Ilera's RAG-grounded eligibility engine as custom tools, so other agents in a
Band room can ask Ilera to assess a caregiver's benefits or look up official program
rules and get back cited, source-linked answers.

Run it as a worker:

    python -m app.integrations.band

It is entirely optional: the synchronous HTTP eligibility flow works without Band, and
this module is only imported when BAND_API_KEY + BAND_AGENT_ID are configured.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, Field

from ..agents.routing import run_routing
from ..config import get_settings
from ..models import CareRecipient, Caregiver, CaseProfile, Household
from ..rag.index import get_index

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are Ilera's Routing Agent, an expert coordinator for U.S. caregiver benefits "
    "(IHSS, Medi-Cal/HCBS, Medicare, Paid Family Leave, VA caregiver support, and caregiver "
    "tax relief). When another agent describes a caregiver's situation, call the "
    "assesseligibility tool to run Ilera's specialist agents and return ranked, source-cited "
    "eligibility findings. Use the searchprogramdocs tool to quote specific official rules. "
    "Always ground your answers in the returned citations (title, page, source URL); never "
    "invent program rules."
)


class AssessEligibilityInput(BaseModel):
    """Assess which caregiver benefit programs a care recipient likely qualifies for. Returns ranked programs with status, rationale, next steps, and citations to official sources."""

    recipient_age: int | None = Field(default=None, description="Age of the care recipient")
    veteran: bool = Field(default=False, description="Is the care recipient a U.S. veteran?")
    insurance: str = Field(default="unknown", description="medi-cal | medicare | private | none | unknown")
    conditions: list[str] = Field(default_factory=list, description="Medical conditions, e.g. dementia")
    care_needs: list[str] = Field(default_factory=list, description="Daily care needs, e.g. bathing, meals")
    caregiver_relationship: str = Field(default="", description="Caregiver's relationship, e.g. daughter")
    caregiver_employment: str = Field(default="", description="Caregiver employment status, e.g. full-time")
    household_size: int | None = Field(default=None, description="Number of people in the household")
    household_income_monthly: float | None = Field(default=None, description="Total monthly household income (USD)")
    goals: list[str] = Field(default_factory=list, description="Caregiver goals, e.g. keep recipient at home")


class SearchProgramDocsInput(BaseModel):
    """Search Ilera's official program-documentation knowledge base and return matching passages with titles, page numbers, and source URLs."""

    query: str = Field(description="What to look up, e.g. 'IHSS hours assessment'")
    program: str | None = Field(
        default=None,
        description="Optional program filter: ihss | medical | medicare | pfl | va | tax | federal_routing",
    )


def _profile_from_input(inp: AssessEligibilityInput) -> CaseProfile:
    return CaseProfile(
        id="band",
        care_recipient=CareRecipient(
            age=inp.recipient_age,
            veteran=inp.veteran,
            insurance=inp.insurance if inp.insurance in
            {"medi-cal", "medicare", "private", "none", "unknown"} else "unknown",
            conditions=inp.conditions,
            care_needs=inp.care_needs,
        ),
        caregiver=Caregiver(
            relationship=inp.caregiver_relationship,
            employment_status=inp.caregiver_employment,
        ),
        household=Household(size=inp.household_size, income_monthly=inp.household_income_monthly),
        goals=inp.goals,
    )


def _assess_eligibility_sync(inp: AssessEligibilityInput) -> dict:
    routing = run_routing(_profile_from_input(inp))
    return {
        "programs": [
            {
                "program": r.program,
                "status": r.status,
                "confidence": round(r.confidence, 2),
                "rationale": r.rationale,
                "next_steps": r.next_steps,
                "citations": [
                    {"title": c.title, "page": c.page, "source_url": c.source_url}
                    for c in r.citations
                ],
            }
            for r in routing.results
        ],
        "follow_up_questions": [q.prompt for q in routing.followups],
        "strategy_notes": routing.strategy_notes,
    }


def _search_docs_sync(inp: SearchProgramDocsInput) -> dict:
    hits = get_index().search(inp.query, k=5, program=inp.program)
    return {
        "passages": [
            {
                "program": h.program,
                "title": h.title or h.source,
                "page": h.page,
                "source_url": h.source_url,
                "text": h.text[:600],
            }
            for h in hits
        ]
    }


async def assess_eligibility(inp: AssessEligibilityInput) -> dict:
    return await asyncio.to_thread(_assess_eligibility_sync, inp)


async def search_program_docs(inp: SearchProgramDocsInput) -> dict:
    return await asyncio.to_thread(_search_docs_sync, inp)


def build_agent():
    """Construct the Band agent with Ilera's tools. Raises if Band isn't configured."""
    from band import Agent
    from band.adapters.anthropic import AnthropicAdapter

    settings = get_settings()
    if not settings.has_band:
        raise RuntimeError("Band not configured (need BAND_API_KEY and BAND_AGENT_ID)")
    if not settings.anthropic_api_key:
        raise RuntimeError("Band agent needs ANTHROPIC_API_KEY for reasoning")

    adapter = AnthropicAdapter(
        model=settings.anthropic_model,
        system_prompt=_SYSTEM_PROMPT,
        provider_key=settings.anthropic_api_key,
        additional_tools=[
            (AssessEligibilityInput, assess_eligibility),
            (SearchProgramDocsInput, search_program_docs),
        ],
    )
    return Agent.create(
        adapter=adapter,
        agent_id=settings.band_agent_id,
        api_key=settings.band_api_key,
        ws_url=settings.band_ws_url,
        rest_url=settings.band_rest_url.rstrip("/"),
    )


async def _run() -> None:
    agent = build_agent()
    await agent.start()
    logger.info("Ilera routing agent connected to Band as %r", agent.agent_name)
    print(f"Ilera routing agent connected to Band as {agent.agent_name!r}. Listening ...")
    try:
        await agent.run_forever()
    finally:
        await agent.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
