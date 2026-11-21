"""Inter-program eligibility analyzer.

Caregiver benefits interact: IHSS generally requires active Medi-Cal, Medicare is a
secondary payer to Medi-Cal, IHSS/waiver wages can be federally tax-excludable under
IRS Notice 2014-7, etc. This module grounds those cross-program interactions in the
**inter-eligibility advising documents** in the corpus and returns cited notes.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.eligibility.agents.model_settings import REASONING_EFFORT, RESEARCH_MAX_TOKENS
from app.cases.models import CaseProfile, Citation, InteractionNote
from app.rag.index import get_index
from app.rag.scope import profile_scope
from app.eligibility.agents.output_contracts import InteractionsOutput

# Program scopes whose docs describe how programs interact (coordination / routing / tax).
INTERACTION_SCOPES = ["federal_routing", "medicare", "tax", "medical"]

_SYSTEM = (
    "You are Ilera's inter-program eligibility coordinator. Using ONLY the official "
    "coordination/advising documentation provided, identify how the caregiver's likely "
    "benefit programs interact: prerequisites (e.g. IHSS requires active Medi-Cal), payer "
    "ordering (e.g. Medicare secondary to Medi-Cal), income/tax interactions (e.g. IRS "
    "Notice 2014-7 waiver-payment exclusion), and the best sequence to apply. Be specific "
    "and never invent rules not supported by the documentation."
    " Return at most 3 decision-changing interactions and 150 words of note/action "
    "text total. Each note and action is at most 180 characters. No background, "
    "repeated caveats or exhaustive checklist. Use an empty list when none is supported."
)

_SCHEMA_HINT = (
    'Return a JSON object: {"interactions": [{"note": str, "programs": [str], '
    '"action": str, "source_titles": [str]}]}. `note` states the interaction; `programs` '
    "lists the programs involved; `action` is the recommended sequencing/step (may be empty); "
    "`source_titles` must be titles taken verbatim from the provided documentation."
)


def _retrieve(programs: list[str], profile: CaseProfile, k_per_scope: int = 3):
    index = get_index()
    query = (
        "how do these caregiver benefit programs interact, prerequisites, payer order, "
        "income and tax treatment, and application sequence: " + ", ".join(programs)
    )
    hits = []
    seen = set()
    for scope in INTERACTION_SCOPES:
        for h in index.search(query, k=k_per_scope, scope=profile_scope(profile, scope)):
            key = (h.document_id or h.source, h.page)
            if key not in seen:
                seen.add(key)
                hits.append(h)
    return hits


def _citation(h) -> Citation:
    return Citation(
        document_id=h.document_id or h.source,
        title=h.title or h.source,
        source_url=h.source_url,
        page=h.page,
        program=h.program,
    )


def analyze_program_interactions(
    profile: CaseProfile, programs: list[str]
) -> list[InteractionNote]:
    """Return cited cross-program interaction notes for the given active program names."""
    active = [p for p in dict.fromkeys(programs) if p]
    summary = ", ".join(active)
    return _analyze(profile, active, summary)


def _analyze(
    profile: CaseProfile, active: list[str], summary: str
) -> list[InteractionNote]:
    active_set = set(active)
    if len(active_set) < 2:
        return []
    s = get_settings()
    hits = _retrieve(active, profile)
    if not hits:
        return []
    context = "\n\n".join(
        f"[{h.title or h.source}" + (f", p.{h.page}" if h.page else "") + f"] Policy metadata: {h.policy}\n{h.text}"
        for h in hits
    )

    def match_hits(title: str):
        """Tolerant match of a model-cited title to retrieved hits (case/substring)."""
        t = (title or "").strip().casefold()
        if not t:
            return []
        out = [h for h in hits if t in (h.title or h.source).casefold()
               or (h.title or h.source).casefold() in t]
        return out[:1]

    user = (
        f"ACTIVE PROGRAMS AND STATUS: {summary}\n\n"
        f"CAREGIVER CASE PROFILE (JSON):\n{profile.model_dump_json(indent=2)}\n\n"
        f"INTER-ELIGIBILITY ADVISING DOCUMENTATION:\n{context}\n\n{_SCHEMA_HINT}"
    )
    from openai import OpenAI
    from pydantic_ai.profiles.openai import OpenAIJsonSchemaTransformer
    client = OpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url)
    resp = client.chat.completions.create(
        model=s.openai_model,
        max_completion_tokens=RESEARCH_MAX_TOKENS,
        reasoning_effort=REASONING_EFFORT,
        response_format={"type": "json_schema", "json_schema": {
            "name": "program_interactions", "strict": True,
            "schema": OpenAIJsonSchemaTransformer(InteractionsOutput.model_json_schema(), strict=True).walk(),
        }},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    choice = resp.choices[0]
    if choice.finish_reason != "stop" or choice.message.refusal or not choice.message.content:
        raise ValueError("Incomplete interaction output")
    data = InteractionsOutput.model_validate_json(choice.message.content).model_dump()
    notes: list[InteractionNote] = []
    for item in data.get("interactions", []) or []:
        note = str(item.get("note", "")).strip()
        if not note:
            continue
        seen = set()
        citations = []
        for t in item.get("source_titles", []) or []:
            for h in match_hits(t):
                key = (h.document_id or h.source, h.page)
                if key not in seen:
                    seen.add(key)
                    citations.append(_citation(h))
        notes.append(InteractionNote(
            note=note,
            programs=[str(p) for p in item.get("programs", []) or []],
            action=str(item.get("action", "")),
            citations=citations,
        ))
    return notes
