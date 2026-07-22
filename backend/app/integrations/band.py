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
from ..agents.specialists import ALL_SPECIALISTS
from ..config import get_settings
from ..models import CaseProfile
from ..rag.index import get_index

# Band/pydantic-ai are only required when agents actually run, but the names must live at
# module scope so the string annotations on the context-aware tools (e.g.
# "RunContext[AgentToolsProtocol]") resolve via get_type_hints when pydantic-ai registers them.
try:  # pragma: no cover - optional dependency at import time
    from band.core.protocols import AgentToolsProtocol
    from pydantic_ai import RunContext
except Exception:  # pragma: no cover
    AgentToolsProtocol = None
    RunContext = None

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
    "assess eligibility yourself. At the start of a case you post a structured summary of the "
    "caregiver's intake and @mention every program specialist so they each evaluate the case. "
    "Your specialists are: ilera-ihss, ilera-medi-cal, ilera-medicare, ilera-pfl, ilera-va, "
    "ilera-tax.\n\n"
    "Each specialist returns a complete response: a match level, notes, and any cross-program "
    "coordination. When you are told that ALL specialists have returned their complete "
    "responses (their findings will be included in that message), do this:\n"
    "1. Optionally call searchprogramdocs to ground any cross-program sequencing "
    "(prerequisites, payer order, tax treatment, application order) in the coordination docs.\n"
    "2. Synthesize ONE clear, human-facing APPLICATION STRATEGY for the caregiver: which "
    "programs to pursue and in what order, why, how the programs interact, and the concrete "
    "next steps to qualify for and apply to the strongest options. Attribute claims to the "
    "specialists and keep citations. Never invent program rules.\n"
    "3. Submit it by calling the submit_strategy tool with the full strategy text. Do this "
    "exactly once. Do not @mention specialists in the strategy."
)


def _specialist_prompt(program: str) -> str:
    return (
        f"You are Ilera's expert specialist for {program}. You assess ONLY {program} "
        f"eligibility, grounded strictly in {program}'s official and informational "
        "documentation.\n\n"
        "The routing agent will post a case with the caregiver's and care recipient's intake "
        "details, including their STATE and COUNTY, and @mention you. When mentioned, be "
        "economical with tool calls — do NOT re-look-up what you already have:\n"
        f"1. Call lookupprogramdocs ONCE (at most twice) to ground yourself in {program}'s rules "
        "and to get exact citations (title, page, source URL).\n"
        f"2. Evaluate THIS case for {program}, explicitly factoring in the recipient's state and "
        "county and how they affect eligibility, program availability, and the office/process "
        "(many programs are county-administered).\n"
        "3. Determine a match level on this scale: none, low, medium, likely, very_likely — plus "
        "a few short notes explaining the determination, with citations.\n"
        "4. CROSS-ELIGIBILITY (only if clearly warranted): if another program creates a real "
        "cross-eligibility issue or opportunity (e.g. a prerequisite, payer order, income/tax "
        "interaction), @mention that program's specialist agent by name (band_send_message) and "
        "exchange AT MOST one or two short messages to align on a plan. Only mention specialists "
        "that exist in the room. Do not loop; if in doubt, skip the dialogue and note it instead.\n"
        "5. Then submit your COMPLETE response by calling the submit_complete_response tool with "
        "your match_level, notes, the list of cross_programs you coordinated with, and citations. "
        "Call it exactly once, as your final action. "
        f"If the case is clearly outside {program}, still submit with match_level 'none' and a "
        "one-line note."
    )


_MATCH_LEVELS = {"none", "low", "medium", "likely", "very_likely"}


# ---------------------------------------------------------------------------
# Tool input models (the class docstring becomes the tool description shown to the LLM)
# ---------------------------------------------------------------------------
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


# --- Routing (cross-program) handlers -------------------------------------
def _search_docs_sync(inp: SearchProgramDocsInput) -> dict:
    hits = get_index().search(inp.query, k=5, program=inp.program)
    return {"passages": _passages(hits)}


# --- Specialist (single-program) handlers ---------------------------------
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


# How many times the OpenAI client transparently retries a throttled (429) call,
# honoring Azure's Retry-After header with exponential backoff. This absorbs a rate-limit
# spike *inside* the single call so the agent turn never fails — which is what otherwise
# makes Band re-deliver the message and re-run the whole turn (RAG + reasoning) from
# scratch, multiplying load into a retry storm.
_OPENAI_MAX_RETRIES = 6
_OPENAI_TIMEOUT_SECONDS = 90.0


def _openai_model():
    """Build a pydantic-ai model backed by an OpenAI-compatible client configured with
    rate-limit backoff. Band's PydanticAIAdapter accepts a model instance (not just a
    provider string), so we can inject retry/timeout behavior the bare "openai:<model>"
    string cannot express."""
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    s = get_settings()
    client = AsyncOpenAI(
        api_key=s.openai_api_key,
        base_url=s.openai_base_url or None,
        max_retries=_OPENAI_MAX_RETRIES,
        timeout=_OPENAI_TIMEOUT_SECONDS,
    )
    return OpenAIChatModel(s.openai_model, provider=OpenAIProvider(openai_client=client))


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
    """Build the framework adapter. `tools` is a mixed list: (InputModel, handler)
    tuples for plain tools, and native pydantic-ai tool callables (functions taking
    `ctx: RunContext[AgentToolsProtocol]`) for context-aware tools that need the
    room_id (e.g. submit_complete_response / submit_strategy)."""
    from band import AdapterFeatures, Capability

    # `prompt`/`custom_section` (not `system_prompt`) so the SDK's base instructions are
    # included — they teach the agent to use band_send_message, handle mentions, look up
    # peers, etc. Passing the full system prompt would bypass all of that and leave the
    # agent unable to communicate on the platform.
    features = AdapterFeatures(
        capabilities=frozenset({Capability.CONTACTS, Capability.MEMORY}),
    )
    s = get_settings()
    if llm.provider() == "openai":
        from band.adapters.pydantic_ai import PydanticAIAdapter

        _configure_openai_env()
        pai_tools = [
            t if callable(t) and not isinstance(t, tuple) else _to_pai_tool(t[0], t[1])
            for t in tools
        ]
        return PydanticAIAdapter(
            model=_openai_model(),
            custom_section=prompt,
            additional_tools=pai_tools,
            features=features,
        )
    from band.adapters.anthropic import AnthropicAdapter

    # Anthropic path only supports the (InputModel, handler) CustomToolDef form; native
    # ctx-aware callables (room-aware submit tools) are openai-only here.
    tuple_tools = [t for t in tools if isinstance(t, tuple)]
    return AnthropicAdapter(
        model=s.anthropic_model,
        prompt=prompt,
        provider_key=s.anthropic_api_key,
        additional_tools=tuple_tools,
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
    from ..store import record_strategy

    async def submit_strategy(ctx: "RunContext[AgentToolsProtocol]", strategy: str) -> str:
        """Submit the final synthesized application strategy for the caregiver. Call once,
        after ALL specialists have returned complete responses. `strategy` is the full
        human-facing plan (which programs, in what order, why, next steps)."""
        room_id = getattr(ctx.deps, "room_id", "") or ""
        case_id = await asyncio.to_thread(record_strategy, room_id, strategy)
        return "strategy recorded" if case_id else "could not resolve the case for this room"

    tools = [(SearchProgramDocsInput, _wrap(_search_docs_sync)), submit_strategy]
    return _make_agent(_adapter(_ROUTING_PROMPT, tools), creds, skip_backlog=skip_backlog)


def build_specialist_agent(doc_key: str, creds: dict, *, skip_backlog: bool = False):
    from ..store import record_finding

    program = _PROGRAM_NAMES[doc_key]

    async def lookup(inp: LookupProgramDocsInput) -> dict:
        return await asyncio.to_thread(_lookup_sync, doc_key, inp)

    async def submit_complete_response(
        ctx: "RunContext[AgentToolsProtocol]",
        match_level: str,
        notes: list[str],
        cross_programs: list[str] | None = None,
        citations: list[str] | None = None,
    ) -> str:
        """Submit your FINAL, complete eligibility determination for this program back to the
        routing agent. Call exactly once, after any cross-eligibility dialogue is resolved.
        match_level must be one of: none, low, medium, likely, very_likely. notes is a short
        list explaining the determination; citations are "Title (page) — URL" strings."""
        room_id = getattr(ctx.deps, "room_id", "") or ""
        lvl = match_level if match_level in _MATCH_LEVELS else "medium"
        case_id = await asyncio.to_thread(
            record_finding, room_id, doc_key, program, lvl, notes or [],
            cross_programs or [], citations or [],
        )
        # Post a (non-mention) confirmation so the completion shows on the room timeline
        # without prematurely re-triggering the routing agent; the server orchestrator
        # triggers routing once all specialists are complete.
        try:
            summary = "; ".join((notes or [])[:2])
            await ctx.deps.send_message(f"[complete] {program}: match={lvl}. {summary}")
        except Exception:
            logger.debug("submit_complete_response: confirmation message failed", exc_info=True)
        return "finding recorded" if case_id else "could not resolve the case for this room"

    tools = [(LookupProgramDocsInput, lookup), submit_complete_response]
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


# ---------------------------------------------------------------------------
# Per-case room orchestration
# ---------------------------------------------------------------------------
def _rest_client(api_key: str):
    from band.client.rest import AsyncRestClient

    return AsyncRestClient(api_key=api_key, base_url=get_settings().band_rest_url.rstrip("/"))


def _seed_content(profile: CaseProfile, mention_ids: list[str]) -> str:
    cr = profile.care_recipient
    cg = profile.caregiver
    hh = profile.household
    mentions = " ".join(f"@[[{aid}]]" for aid in mention_ids)
    lines = [
        f"{mentions} New caregiver case — please evaluate this case for your program.",
        "",
        "You are each an expert in your program. Using your official and informational "
        "knowledge base, evaluate this specific case (factoring in the recipient's STATE and "
        "COUNTY and how they affect eligibility) and determine: (a) an eligibility match level "
        "(none, low, medium, likely, very_likely); (b) a few notes explaining it; (c) if another "
        "program raises a cross-eligibility issue, @mention that specialist and plan together to "
        "maximize benefits and ensure the caregiver qualifies for at least one program. When "
        "done, call submit_complete_response.",
        "",
        "== CARE RECIPIENT ==",
        f"Name: {cr.name or 'n/a'}",
        f"Age: {cr.age if cr.age is not None else 'unknown'}",
        f"State: {cr.state or 'unknown'}    County: {cr.county or 'unknown'}",
        f"Insurance / coverage: {cr.insurance}",
        f"Veteran: {cr.veteran}",
        f"Conditions: {', '.join(cr.conditions) or 'unspecified'}",
        f"Care needs (ADLs): {', '.join(cr.care_needs) or 'unspecified'}",
        f"Current benefits: {', '.join(cr.current_benefits) if cr.current_benefits else 'none reported'}",
        "",
        "== CAREGIVER ==",
        f"Name: {cg.name or 'n/a'}",
        f"Relationship to recipient: {cg.relationship or 'unspecified'}",
        f"Employment status: {cg.employment_status or 'unspecified'}",
        f"Weekly caregiving hours: {cg.hours_per_week if cg.hours_per_week is not None else 'unspecified'}",
        f"Co-resides with recipient: {profile.answers.get('caregiver.coresidence', 'unspecified')}",
        "",
        "== HOUSEHOLD ==",
        f"Size: {hh.size if hh.size is not None else 'unknown'}",
        f"Monthly income: ${hh.income_monthly if hh.income_monthly is not None else 'unknown'}",
    ]
    return "\n".join(lines)


async def start_case_room(profile: CaseProfile) -> tuple[str, list[str]]:
    """Create one Band room for this case, add the routing agent + every specialist, and map the
    room to the case. Does NOT post the seed — specialists are seeded in waves afterwards (see
    seed_specialists) so we don't fan out to every specialist at once and blow the LLM rate limit.

    Returns (chat_id, specialist_doc_keys). Raises if Band/routing is not configured.
    """
    from band.client.rest import (
        ChatRoomRequest,
        DEFAULT_REQUEST_OPTIONS,
        ParticipantRequest,
    )

    from ..store import map_room_to_case

    registry = load_registry()
    routing = registry.get("routing")
    if not routing:
        raise RuntimeError("Band routing agent not configured")
    specialists = [k for k in registry if k in _SPECIALISTS]
    if not specialists:
        raise RuntimeError("No Band specialist agents configured")

    routing_client = _rest_client(routing["api_key"])
    chat = await routing_client.agent_api_chats.create_agent_chat(
        chat=ChatRoomRequest(), request_options=DEFAULT_REQUEST_OPTIONS
    )
    chat_id = chat.data.id
    map_room_to_case(chat_id, profile.id)

    for key in specialists:
        try:
            await routing_client.agent_api_participants.add_agent_chat_participant(
                chat_id,
                participant=ParticipantRequest(
                    participant_id=registry[key]["agent_id"], role="member"
                ),
                request_options=DEFAULT_REQUEST_OPTIONS,
            )
        except Exception:
            logger.debug("add participant %s conflict/ignored", key, exc_info=True)

    logger.info("Band case room %s created with %d specialists", chat_id, len(specialists))
    return chat_id, specialists


async def seed_specialists(profile: CaseProfile, chat_id: str, batch: list[str]) -> None:
    """Post the structured seed @mentioning only the specialists in `batch`, prompting just
    those agents to evaluate. Dispatching in small waves (rather than mentioning all specialists
    in one message) keeps concurrent LLM calls low so we stay under the rate limit."""
    from band.client.rest import (
        ChatMessageRequest,
        ChatMessageRequestMentionsItem,
        DEFAULT_REQUEST_OPTIONS,
    )

    registry = load_registry()
    routing = registry.get("routing")
    if not routing:
        raise RuntimeError("Band routing agent not configured")
    keys = [k for k in batch if k in registry]
    if not keys:
        return

    routing_client = _rest_client(routing["api_key"])
    mention_ids = [registry[k]["agent_id"] for k in keys]
    mentions = [
        ChatMessageRequestMentionsItem(id=registry[k]["agent_id"], handle=_SPECIALIST_NAMES[k])
        for k in keys
    ]
    await routing_client.agent_api_messages.create_agent_chat_message(
        chat_id,
        message=ChatMessageRequest(content=_seed_content(profile, mention_ids), mentions=mentions),
        request_options=DEFAULT_REQUEST_OPTIONS,
    )
    logger.info("Band room %s seeded wave: %s", chat_id, ", ".join(keys))


async def trigger_synthesis(chat_id: str, findings_summary: str) -> None:
    """Post a message @mentioning the routing agent telling it all specialists are complete,
    so it synthesizes the application strategy and calls submit_strategy."""
    from band.client.rest import (
        ChatMessageRequest,
        ChatMessageRequestMentionsItem,
        DEFAULT_REQUEST_OPTIONS,
    )

    registry = load_registry()
    routing = registry.get("routing")
    if not routing:
        return
    client = _rest_client(routing["api_key"])
    me = await client.agent_api_identity.get_agent_me(request_options=DEFAULT_REQUEST_OPTIONS)
    handle = getattr(getattr(me, "data", me), "handle", "") or "ilera-routing"
    content = (
        f"@[[{routing['agent_id']}]] All specialists have returned complete responses. "
        "Synthesize the application strategy now and call submit_strategy.\n\n"
        f"{findings_summary}"
    )
    await client.agent_api_messages.create_agent_chat_message(
        chat_id,
        message=ChatMessageRequest(
            content=content,
            mentions=[ChatMessageRequestMentionsItem(id=routing["agent_id"], handle=handle)],
        ),
        request_options=DEFAULT_REQUEST_OPTIONS,
    )


async def drain_stale_rooms() -> int:
    """Mark every leftover pending/processing/failed message in all existing rooms as
    processed, per agent. Freshly started agents otherwise re-sweep this backlog on startup
    (old orphan rooms stay open), which floods the LLM and exhausts rate limits, starving the
    current case. Call once at startup BEFORE agents connect and before any case room exists.
    """
    from band.client.rest import DEFAULT_REQUEST_OPTIONS

    registry = load_registry()
    drained = 0
    for key, creds in registry.items():
        if key in ("caregiver", "user"):
            continue
        client = _rest_client(creds["api_key"])
        try:
            chats = await client.agent_api_chats.list_agent_chats(
                page=1, page_size=200, request_options=DEFAULT_REQUEST_OPTIONS
            )
        except Exception:
            logger.debug("drain: could not list chats for %s", key, exc_info=True)
            continue
        for chat in (getattr(chats, "data", None) or []):
            for status in ("processing", "failed", "pending"):
                try:
                    msgs = await client.agent_api_messages.list_agent_messages(
                        chat.id, status=status, page_size=200,
                        request_options=DEFAULT_REQUEST_OPTIONS,
                    )
                except Exception:
                    continue
                for m in (getattr(msgs, "data", None) or []):
                    try:
                        await client.agent_api_messages.mark_agent_message_processed(
                            chat.id, m.id, request_options=DEFAULT_REQUEST_OPTIONS
                        )
                        drained += 1
                    except Exception:
                        logger.debug("drain: mark processed failed", exc_info=True)
    logger.info("Band startup drain: marked %d stale message(s) processed", drained)
    return drained


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
