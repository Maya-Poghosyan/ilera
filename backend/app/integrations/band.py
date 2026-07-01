"""Band integration — runs each Ilera specialist as its own Band agent.

Every program group (IHSS, Medi-Cal, Medicare, PFL, VA, Tax) is registered as a separate
agent on the Band platform (https://docs.band.ai) and connects over a websocket. Each
specialist agent is grounded ONLY in its program's documentation and exposes program-scoped
tools, so other agents in a Band room can consult, say, the IHSS specialist directly. A
"routing" coordinator agent exposes cross-program tools.

Credentials come from a JSON registry (default: backend/band_agents.json), mapping each
program group to its Band agent_id + api_key:

    {
      "routing":  {"agent_id": "...", "api_key": "..."},
      "ihss":     {"agent_id": "...", "api_key": "..."},
      "medical":  {"agent_id": "...", "api_key": "..."},
      "medicare": {"agent_id": "...", "api_key": "..."},
      "pfl":      {"agent_id": "...", "api_key": "..."},
      "va":       {"agent_id": "...", "api_key": "..."},
      "tax":      {"agent_id": "...", "api_key": "..."}
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

from ..agents.interactions import analyze_interactions
from ..agents.routing import run_routing
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
    "You are Ilera's Routing Agent, the coordinator for U.S. caregiver benefits. You work with "
    "program specialist agents in your Band organization: ilera-ihss, ilera-medi-cal, "
    "ilera-medicare, ilera-pfl, ilera-va, ilera-tax.\n\n"
    "When another agent describes a caregiver's situation:\n"
    "1. Call assesseligibility to run all specialists and get ranked, source-cited findings plus "
    "cross-program interaction notes.\n"
    "2. To dig deeper on one program, CONSULT that specialist directly: use band_lookup_peers to "
    "find it, band_add_participant to bring it into the room, and band_send_message to ask your "
    "question — then incorporate its reply.\n"
    "3. Call analyzeinteractions to explain how the programs interact (prerequisites, payer order, "
    "tax treatment, application sequence), grounded in the inter-eligibility advising documents.\n"
    "Ground every claim in citations (title, page, source URL); never invent program rules."
)


def _specialist_prompt(program: str) -> str:
    return (
        f"You are Ilera's {program} specialist agent, part of a Band team coordinated by the "
        "routing agent. You ONLY assess eligibility for "
        f"{program} and answer questions about it, grounded strictly in {program}'s official "
        "documentation. When the routing agent (or another agent) messages you in a room, answer "
        "their question: call assesseligibility to evaluate the caregiver's situation for your "
        "program, and lookupprogramdocs to quote the official rules, then reply with "
        "band_send_message. Always cite the source (title, page, URL). If a question is outside "
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
    goals: list[str] = Field(default_factory=list, description="Caregiver goals, e.g. keep recipient at home")


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
    """Explain how the caregiver's benefit programs interact — prerequisites, payer order, income/tax treatment, and the best application sequence — grounded in the official inter-eligibility advising documents with citations."""


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
        goals=inp.goals,
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
def _assess_all_sync(inp: AssessEligibilityInput) -> dict:
    routing = run_routing(_profile_from_input(inp))
    return {
        "programs": [_result_dict(r) for r in routing.results],
        "follow_up_questions": [q.prompt for q in routing.followups],
        "strategy_notes": routing.strategy_notes,
        "interactions": [_interaction_dict(n) for n in routing.interaction_notes],
    }


def _interactions_sync(inp: AnalyzeInteractionsInput) -> dict:
    profile = _profile_from_input(inp)
    results = [a.assess(profile) for a in _SPECIALISTS.values()]
    notes = analyze_interactions(profile, results)
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
def _adapter(prompt: str, tools):
    from band import AdapterFeatures, Capability
    from band.adapters.anthropic import AnthropicAdapter

    # Use `prompt` (not `system_prompt`) so the SDK's base instructions are
    # included — they teach the agent to use band_send_message, handle
    # mentions, look up peers, etc.  Passing `system_prompt` would bypass
    # all of that and leave the agent unable to communicate on the platform.
    features = AdapterFeatures(capabilities=frozenset({Capability.CONTACTS, Capability.MEMORY}))
    return AnthropicAdapter(
        model=get_settings().anthropic_model,
        prompt=prompt,
        provider_key=get_settings().anthropic_api_key,
        additional_tools=tools,
        features=features,
    )


def _make_agent(adapter, creds: dict):
    from band import Agent

    s = get_settings()
    return Agent.create(
        adapter=adapter,
        agent_id=creds["agent_id"],
        api_key=creds["api_key"],
        ws_url=s.band_ws_url,
        rest_url=s.band_rest_url.rstrip("/"),
    )


def build_routing_agent(creds: dict):
    tools = [
        (AssessEligibilityInput, _wrap(_assess_all_sync)),
        (AnalyzeInteractionsInput, _wrap(_interactions_sync)),
        (SearchProgramDocsInput, _wrap(_search_docs_sync)),
    ]
    return _make_agent(_adapter(_ROUTING_PROMPT, tools), creds)


def build_specialist_agent(doc_key: str, creds: dict):
    program = _PROGRAM_NAMES[doc_key]

    async def assess(inp: AssessEligibilityInput) -> dict:
        return await asyncio.to_thread(_assess_one_sync, doc_key, inp)

    async def lookup(inp: LookupProgramDocsInput) -> dict:
        return await asyncio.to_thread(_lookup_sync, doc_key, inp)

    tools = [(AssessEligibilityInput, assess), (LookupProgramDocsInput, lookup)]
    return _make_agent(_adapter(_specialist_prompt(program), tools), creds)


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


def build_agents() -> list:
    """Construct every configured Band agent (routing coordinator + per-program specialists)."""
    if not get_settings().anthropic_api_key:
        raise RuntimeError("Band agents need ANTHROPIC_API_KEY for reasoning")
    registry = load_registry()
    if not registry:
        raise RuntimeError(
            "No Band agents configured. Provide band_agents.json or BAND_API_KEY + BAND_AGENT_ID."
        )
    agents = []
    for key, creds in registry.items():
        if key in _SPECIALISTS:
            agents.append((key, build_specialist_agent(key, creds)))
        elif key == "routing":
            agents.append((key, build_routing_agent(creds)))
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
