"""Band integration — runs each Ilera specialist as its own Band agent.

Every program group (IHSS, Medi-Cal, Medicare, PFL, VA, Tax) is registered as a separate
agent on the Band platform (https://docs.band.ai) and connects over a websocket. Each
specialist agent is grounded ONLY in its program's documentation and exposes program-scoped
tools.

Band is the real coordination substrate: the "routing" coordinator agent does NOT assess
eligibility itself. When the caregiver describes their situation, the routing agent consults
the relevant specialists ONE AT A TIME over the shared room (band_send_message), gathers
their cited replies, reasons about cross-program interactions, and delivers a single
synthesized strategy back to the caregiver. Specialists answer only their own program.

Credentials come from a JSON registry (default: backend/band_agents.json), mapping each
program group to its Band agent_id + api_key. An optional "caregiver" (or "user") identity
lets the server post the seed request as the human, so the routing agent is triggered:

    {
      "routing":   {"agent_id": "...", "api_key": "..."},
      "caregiver": {"agent_id": "...", "api_key": "..."},
      "ihss":      {"agent_id": "...", "api_key": "..."},
      "medical":   {"agent_id": "...", "api_key": "..."},
      "medicare":  {"agent_id": "...", "api_key": "..."},
      "pfl":       {"agent_id": "...", "api_key": "..."},
      "va":        {"agent_id": "...", "api_key": "..."},
      "tax":       {"agent_id": "...", "api_key": "..."}
    }

For backwards-compat, if no registry file exists but BAND_API_KEY + BAND_AGENT_ID are set,
a single "routing" coordinator agent is run.

Run the worker:  python -m app.integrations.band
It is optional: the synchronous HTTP eligibility flow works without Band, and the `band`
package is only imported when the worker actually starts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from pydantic import BaseModel, Field

from .. import llm
from ..agents.interactions import analyze_program_interactions
from ..agents.specialists import ALL_SPECIALISTS
from ..config import get_settings
from ..models import CareRecipient, Caregiver, CaseProfile, EligibilityResult, Household
from ..rag.index import get_index

logger = logging.getLogger(__name__)

# doc_key -> (program display name, specialist instance)
_SPECIALISTS = {cls().doc_key: cls() for cls in ALL_SPECIALISTS}
_PROGRAM_NAMES = {k: a.program for k, a in _SPECIALISTS.items()}

_SPECIALIST_NAMES = {
    "ihss": "ilera-ihss", "medical": "ilera-medi-cal", "medicare": "ilera-medicare",
    "pfl": "ilera-pfl", "va": "ilera-va", "tax": "ilera-tax",
}

_ROUTING_PROMPT = (
    "You are Ilera's Routing Agent, the coordinator for U.S. caregiver benefits. You do NOT "
    "assess eligibility yourself — you have no assessment tool. Your job is to consult the "
    "program specialist agents in your Band room and synthesize their answers for the "
    "caregiver. Your specialists are: ilera-ihss, ilera-medi-cal, ilera-medicare, ilera-pfl, "
    "ilera-va, ilera-tax.\n\n"
    "When the caregiver (the human in the room) describes their situation:\n"
    "1. Decide which programs are plausibly relevant to this caregiver.\n"
    "2. CONSULT the relevant specialists ONE AT A TIME. For each: use band_lookup_peers to find "
    "the specialist, band_add_participant to ensure it is in the room, then band_send_message "
    "mentioning ONLY that one specialist with a specific, scoped question about the caregiver's "
    "situation. WAIT for that specialist's cited reply before moving to the next one. Do not "
    "@mention several specialists in one message, and do not broadcast.\n"
    "3. After you have gathered the specialists' findings, call analyzeinteractions with the list "
    "of programs the specialists found relevant to explain how they interact (prerequisites, "
    "payer order, tax treatment, application sequence), grounded in the coordination/advising "
    "documents. Use searchprogramdocs for any additional coordination lookups.\n"
    "4. Deliver ONE final, synthesized benefit strategy addressed to the CAREGIVER (the human). "
    "This is a human-facing deliverable: do NOT @mention any specialist agents in it. Attribute "
    "each claim to the specialist that provided it and keep their citations (title, page, source "
    "URL). Never invent program rules."
)


def _specialist_prompt(program: str) -> str:
    return (
        f"You are Ilera's {program} specialist agent, part of a Band team coordinated by the "
        "routing agent. You ONLY assess eligibility for "
        f"{program} and answer questions about it, grounded strictly in {program}'s official "
        "documentation. The routing agent will message you with a scoped question about a "
        "caregiver's situation. To answer it: call assesseligibility to evaluate the caregiver "
        f"for {program}, and lookupprogramdocs to quote the official rules, then reply with "
        "band_send_message directed back to the routing agent — mention only the routing agent, "
        "do not broadcast or @mention other specialists. Keep your answer scoped to your program "
        "and always cite the source (title, page, URL). If a question is outside "
        f"{program}, say so and defer to the routing agent."
    )


# ---------------------------------------------------------------------------
# Tool input models (the class docstring becomes the tool description shown to the LLM)
# ---------------------------------------------------------------------------
class AssessEligibilityInput(BaseModel):
    """Assess caregiver benefit eligibility for a care recipient. Returns program(s) with status, rationale, next steps, and citations to official sources."""

    recipient_age: int | None = Field(default=None, description="Age of the care recipient")
    veteran: bool = Field(default=False, description="Is the care recipient a U.S. veteran?")
    insurance: str = Field(default="unknown", description="medi-cal | medicare | private | none | unknown")
    conditions: list[str] = Field(default_factory=list, description="Medical conditions, e.g. dementia")
    care_needs: list[str] = Field(default_factory=list, description="Daily care needs, e.g. bathing, meals")
    caregiver_relationship: str = Field(default="", description="Caregiver's relationship, e.g. daughter")
    caregiver_employment: str = Field(default="", description="Caregiver employment status, e.g. full-time")
    household_size: int | None = Field(default=None, description="Number of people in the household")
    household_income_monthly: float | None = Field(default=None, description="Total monthly household income (USD)")


class SearchProgramDocsInput(BaseModel):
    """Search Ilera's official program-documentation knowledge base; returns passages with titles, page numbers, and source URLs."""

    query: str = Field(description="What to look up, e.g. 'IHSS hours assessment'")
    program: str | None = Field(
        default=None,
        description="Optional filter: ihss | medical | medicare | pfl | va | tax | federal_routing",
    )


class LookupProgramDocsInput(BaseModel):
    """Look up this program's official documentation; returns passages with titles, page numbers, and source URLs."""

    query: str = Field(description="What to look up within this program's rules")


class AnalyzeInteractionsInput(AssessEligibilityInput):
    """Explain how the caregiver's benefit programs interact — prerequisites, payer order, income/tax treatment, and the best application sequence — grounded in the official inter-eligibility advising documents with citations. Call this AFTER consulting the specialists, passing the programs their replies found relevant."""

    programs: list[str] = Field(
        default_factory=list,
        description="Program names the specialists found relevant, e.g. ['IHSS', 'Medi-Cal', 'Paid Family Leave']",
    )


def _profile_from_input(inp: AssessEligibilityInput) -> CaseProfile:
    insurance = inp.insurance if inp.insurance in {
        "medi-cal", "medicare", "private", "none", "unknown"
    } else "unknown"
    return CaseProfile(
        id="band",
        care_recipient=CareRecipient(
            age=inp.recipient_age,
            veteran=inp.veteran,
            insurance=insurance,
            conditions=inp.conditions,
            care_needs=inp.care_needs,
        ),
        caregiver=Caregiver(
            relationship=inp.caregiver_relationship,
            employment_status=inp.caregiver_employment,
        ),
        household=Household(size=inp.household_size, income_monthly=inp.household_income_monthly),
    )


def _interaction_dict(n) -> dict:
    return {
        "note": n.note,
        "programs": n.programs,
        "action": n.action,
        "citations": [
            {"title": c.title, "page": c.page, "source_url": c.source_url} for c in n.citations
        ],
    }


def _result_dict(r: EligibilityResult) -> dict:
    return {
        "program": r.program,
        "status": r.status,
        "confidence": round(r.confidence, 2),
        "rationale": r.rationale,
        "next_steps": r.next_steps,
        "follow_up_questions": [q.prompt for q in r.followups],
        "citations": [
            {"title": c.title, "page": c.page, "source_url": c.source_url} for c in r.citations
        ],
    }


# --- Routing (cross-program) handlers -------------------------------------
# The routing agent has NO assess-all tool: it gathers eligibility by consulting the
# specialist agents over the Band room, not by running them in-process. Interactions are
# grounded purely in the coordination/advising corpus from the programs it gathered.
def _interactions_sync(inp: AnalyzeInteractionsInput) -> dict:
    profile = _profile_from_input(inp)
    notes = analyze_program_interactions(profile, inp.programs)
    return {"interactions": [_interaction_dict(n) for n in notes]}


def _search_docs_sync(inp: SearchProgramDocsInput) -> dict:
    hits = get_index().search(inp.query, k=5, program=inp.program)
    return {"passages": _passages(hits)}


# --- Specialist (single-program) handlers ---------------------------------
def _assess_one_sync(doc_key: str, inp: AssessEligibilityInput) -> dict:
    return _result_dict(_SPECIALISTS[doc_key].assess(_profile_from_input(inp)))


def _lookup_sync(doc_key: str, inp: LookupProgramDocsInput) -> dict:
    hits = get_index().search(inp.query, k=5, program=doc_key)
    return {"passages": _passages(hits)}


def _passages(hits) -> list[dict]:
    return [
        {
            "program": h.program,
            "title": h.title or h.source,
            "page": h.page,
            "source_url": h.source_url,
            "text": h.text[:600],
        }
        for h in hits
    ]


# ---------------------------------------------------------------------------
# Agent construction
# ---------------------------------------------------------------------------
def _configure_openai_env() -> None:
    """Expose the app's OpenAI settings to pydantic-ai's OpenAI client, which reads
    OPENAI_API_KEY / OPENAI_BASE_URL from the environment. OPENAI_BASE_URL points at
    an OpenAI-compatible endpoint (e.g. an Azure OpenAI v1 endpoint)."""
    s = get_settings()
    if s.openai_api_key:
        os.environ["OPENAI_API_KEY"] = s.openai_api_key
    if s.openai_base_url:
        os.environ["OPENAI_BASE_URL"] = s.openai_base_url


def _to_pai_tool(input_model, handler):
    """Adapt an (InputModel, async handler) tool into a pydantic-ai tool function.

    pydantic-ai flattens a single Pydantic-model argument into the tool's parameter
    schema, so we can reuse the same input models as the Anthropic path. The tool name
    matches band's convention (model class name minus "Input", lowercased).
    """
    from band.core.protocols import AgentToolsProtocol
    from band.runtime.custom_tools import get_custom_tool_name
    from pydantic_ai import RunContext

    name = get_custom_tool_name(input_model)

    async def _tool(ctx, inp):
        return await handler(inp)

    _tool.__name__ = name
    _tool.__qualname__ = name
    _tool.__doc__ = (input_model.__doc__ or "").strip()
    _tool.__annotations__ = {
        "ctx": RunContext[AgentToolsProtocol],
        "inp": input_model,
        "return": dict,
    }
    return _tool


def _adapter(prompt: str, tools):
    from band import AdapterFeatures, Capability

    # `prompt`/`custom_section` (not `system_prompt`) so the SDK's base instructions are
    # included — they teach the agent to use band_send_message, handle mentions, look up
    # peers, etc. Passing the full system prompt would bypass all of that and leave the
    # agent unable to communicate on the platform.
    features = AdapterFeatures(capabilities=frozenset({Capability.CONTACTS, Capability.MEMORY}))
    s = get_settings()
    if llm.provider() == "openai":
        from band.adapters.pydantic_ai import PydanticAIAdapter

        _configure_openai_env()
        pai_tools = [_to_pai_tool(model, handler) for model, handler in tools]
        return PydanticAIAdapter(
            model=f"openai:{s.openai_model}",
            custom_section=prompt,
            additional_tools=pai_tools,
            features=features,
        )
    from band.adapters.anthropic import AnthropicAdapter

    return AnthropicAdapter(
        model=s.anthropic_model,
        prompt=prompt,
        provider_key=s.anthropic_api_key,
        additional_tools=tools,
        features=features,
    )


def _make_agent(adapter, creds: dict, *, skip_backlog: bool = False):
    from band import Agent, AgentConfig

    s = get_settings()
    config = AgentConfig(auto_subscribe_existing_rooms=not skip_backlog) if skip_backlog else None
    return Agent.create(
        adapter=adapter,
        agent_id=creds["agent_id"],
        api_key=creds["api_key"],
        ws_url=s.band_ws_url,
        rest_url=s.band_rest_url.rstrip("/"),
        config=config,
    )


def build_routing_agent(creds: dict, *, skip_backlog: bool = False):
    tools = [
        (AnalyzeInteractionsInput, _wrap(_interactions_sync)),
        (SearchProgramDocsInput, _wrap(_search_docs_sync)),
    ]
    return _make_agent(_adapter(_ROUTING_PROMPT, tools), creds, skip_backlog=skip_backlog)


def build_specialist_agent(doc_key: str, creds: dict, *, skip_backlog: bool = False):
    program = _PROGRAM_NAMES[doc_key]

    async def assess(inp: AssessEligibilityInput) -> dict:
        return await asyncio.to_thread(_assess_one_sync, doc_key, inp)

    async def lookup(inp: LookupProgramDocsInput) -> dict:
        return await asyncio.to_thread(_lookup_sync, doc_key, inp)

    tools = [(AssessEligibilityInput, assess), (LookupProgramDocsInput, lookup)]
    return _make_agent(_adapter(_specialist_prompt(program), tools), creds, skip_backlog=skip_backlog)


def _wrap(sync_fn):
    async def handler(inp):
        return await asyncio.to_thread(sync_fn, inp)

    return handler


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------
def load_registry() -> dict[str, dict]:
    """Return {group_key: {agent_id, api_key}}. Reads the JSON file, else falls back
    to a single 'routing' agent from BAND_API_KEY/BAND_AGENT_ID."""
    s = get_settings()
    path = s.band_agents_file
    if path and not os.path.isabs(path):
        # resolve relative to the backend/ directory (two levels up from this file)
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), path)
    registry: dict[str, dict] = {}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        for key, entry in raw.items():
            if entry.get("agent_id") and entry.get("api_key"):
                registry[key] = {"agent_id": entry["agent_id"], "api_key": entry["api_key"]}
    if "routing" not in registry and s.has_band:
        registry["routing"] = {"agent_id": s.band_agent_id, "api_key": s.band_api_key}
    return registry


def build_agents(*, skip_backlog: bool = False) -> list:
    """Construct every configured Band agent (routing coordinator + per-program specialists).

    Args:
        skip_backlog: If True, agents won't auto-subscribe to existing rooms on
            startup, preventing them from processing old backlog messages.
    """
    if not llm.available():
        raise RuntimeError(
            "Band agents need an LLM key for reasoning "
            "(ANTHROPIC_API_KEY, or OPENAI_API_KEY with LLM_PROVIDER=openai)"
        )
    registry = load_registry()
    if not registry:
        raise RuntimeError(
            "No Band agents configured. Provide band_agents.json or BAND_API_KEY + BAND_AGENT_ID."
        )
    agents = []
    for key, creds in registry.items():
        if key in _SPECIALISTS:
            agents.append((key, build_specialist_agent(key, creds, skip_backlog=skip_backlog)))
        elif key == "routing":
            agents.append((key, build_routing_agent(creds, skip_backlog=skip_backlog)))
        elif key in ("caregiver", "user"):
            # Human seed identity used by the server to post the caregiver's request; not an
            # autonomous agent, so nothing to build/run here.
            continue
        else:
            logger.warning("Unknown Band agent group %r in registry; skipping", key)
    return agents


# Back-compat: a single routing agent.
def build_agent():
    return build_routing_agent(load_registry()["routing"])


async def _run() -> None:
    agents = build_agents()
    await asyncio.gather(*(a.start() for _, a in agents))
    names = ", ".join(f"{k} ({a.agent_name!r})" for k, a in agents)
    logger.info("Connected %d Band agent(s): %s", len(agents), names)
    print(f"Connected {len(agents)} Band agent(s): {names}\nListening ...")
    try:
        await asyncio.gather(*(a.run_forever() for _, a in agents))
    finally:
        await asyncio.gather(*(a.stop() for _, a in agents), return_exceptions=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
