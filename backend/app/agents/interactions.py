"""Inter-program eligibility analyzer.

Caregiver benefits interact: IHSS generally requires active Medi-Cal, Medicare is a
secondary payer to Medi-Cal, IHSS/waiver wages can be federally tax-excludable under
IRS Notice 2014-7, etc. This module grounds those cross-program interactions in the
**inter-eligibility advising documents** in the corpus and returns cited notes.

It is the shared brain behind both the synchronous HTTP routing flow and the Band
coordinator's `analyzeinteractions` tool. Falls back to a small rule set when no LLM
key is configured so the app still works with zero keys.
"""

from __future__ import annotations

from .. import llm
from ..models import CaseProfile, Citation, EligibilityResult, InteractionNote
from ..rag.index import get_index

# Program scopes whose docs describe how programs interact (coordination / routing / tax).
INTERACTION_SCOPES = ["federal_routing", "medicare", "tax", "medical"]

_SYSTEM = (
    "You are Ilera's inter-program eligibility coordinator. Using ONLY the official "
    "coordination/advising documentation provided, identify how the caregiver's likely "
    "benefit programs interact: prerequisites (e.g. IHSS requires active Medi-Cal), payer "
    "ordering (e.g. Medicare secondary to Medi-Cal), income/tax interactions (e.g. IRS "
    "Notice 2014-7 waiver-payment exclusion), and the best sequence to apply. Be specific "
    "and never invent rules not supported by the documentation."
)

_SCHEMA_HINT = (
    'Return a JSON object: {"interactions": [{"note": str, "programs": [str], '
    '"action": str, "source_titles": [str]}]}. `note` states the interaction; `programs` '
    "lists the programs involved; `action` is the recommended sequencing/step (may be empty); "
    "`source_titles` must be titles taken verbatim from the provided documentation."
)


def _retrieve(programs: list[str], k_per_scope: int = 3):
    index = get_index()
    query = (
        "how do these caregiver benefit programs interact, prerequisites, payer order, "
        "income and tax treatment, and application sequence: " + ", ".join(programs)
    )
    hits = []
    seen = set()
    for scope in INTERACTION_SCOPES:
        for h in index.search(query, k=k_per_scope, program=scope):
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


def _heuristic(results: list[EligibilityResult]) -> list[InteractionNote]:
    notes: list[InteractionNote] = []
    active = {r.program for r in results if r.status in ("likely", "possible")}
    if "IHSS" in active and "Medi-Cal" in active:
        notes.append(InteractionNote(
            note="IHSS eligibility generally requires active Medi-Cal.",
            programs=["IHSS", "Medi-Cal"],
            action="Sequence Medi-Cal first, then apply for IHSS.",
        ))
    if "Medicare" in active and "Medi-Cal" in active:
        notes.append(InteractionNote(
            note="For dual-eligibles, Medicare pays first and Medi-Cal wraps around it.",
            programs=["Medicare", "Medi-Cal"],
            action="Confirm dual-eligible status and Medicare Savings Program enrollment.",
        ))
    if "Caregiver Tax Relief" in active and "IHSS" in active:
        notes.append(InteractionNote(
            note="IHSS provider wages for in-home care to a household member may be "
                 "federally excludable under IRS Notice 2014-7.",
            programs=["IHSS", "Caregiver Tax Relief"],
            action="Check Notice 2014-7 / Medicaid-waiver payment exclusion eligibility.",
        ))
    return notes


def analyze_interactions(
    profile: CaseProfile, results: list[EligibilityResult]
) -> list[InteractionNote]:
    """Return cited cross-program interaction notes for the active programs."""
    active = [r.program for r in results if r.status in ("likely", "possible", "needs_info")]
    if len(active) < 2:
        return []
    if not llm.available():
        return _heuristic(results)
    hits = _retrieve(active)
    if not hits:
        return _heuristic(results)
    context = "\n\n".join(
        f"[{h.title or h.source}" + (f", p.{h.page}" if h.page else "") + f"] {h.text}"
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

    summary = "; ".join(
        f"{r.program}={r.status}({r.confidence:.2f})" for r in results
    )
    user = (
        f"ACTIVE PROGRAMS AND STATUS: {summary}\n\n"
        f"CAREGIVER CASE PROFILE (JSON):\n{profile.model_dump_json(indent=2)}\n\n"
        f"INTER-ELIGIBILITY ADVISING DOCUMENTATION:\n{context}\n\n{_SCHEMA_HINT}"
    )
    try:
        data = llm.complete_json(_SYSTEM, user, max_tokens=1200)
    except Exception:
        return _heuristic(results)
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
    return notes or _heuristic(results)
