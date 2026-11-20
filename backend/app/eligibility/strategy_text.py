"""Normalize the routing agent's strategy into a short list of plain bullets.

The caregiver reads this on the results screen, so it has to survive whatever shape the model
produces: numbered lists, markdown headings, bold emphasis, and the "per the IHSS specialist"
attributions or citation footers that belong to how the answer was produced rather than to the
caregiver's plan. Everything is reduced to one bullet per idea, in order, capped in length —
storage is still a single string, with one bullet per line, so nothing downstream changes shape.
"""

from __future__ import annotations

import re

# A leading list marker in any of the shapes a model reaches for: "- ", "* ", "• ", "1. ", "1) ".
_MARKER = re.compile(r"^\s*(?:[-*•–—]|\(?\d+[.)])\s+")
# Strip single-asterisk italics, backticks, and headings — but preserve ** bold.
_EMPHASIS = re.compile(r"(__|\*(?!\*)|(?<!\*)\*|`|#+)")
# Lines that describe the machinery rather than the plan: internal agent handles, and the
# attribution/citation footers the model appends after the plan itself.
_INTERNAL = re.compile(
    r"(ilera-[a-z-]+|\b(?:sub)?agents?\b|\bspecialists?\b|\brouting agent\b)", re.IGNORECASE
)
_FOOTER = re.compile(
    r"^\s*(attribution|attributions|sources?|citations?|references?|disclaimer)\b[:\s]",
    re.IGNORECASE,
)

_MAX_BULLETS = 10
_MAX_BULLET_CHARS = 240


def to_bullets(strategy: str) -> list[str]:
    """Split a strategy into caregiver-facing bullets, dropping internal commentary."""
    bullets: list[str] = []
    for raw in (strategy or "").splitlines():
        line = _EMPHASIS.sub("", _MARKER.sub("", raw)).strip()
        if not line or _FOOTER.match(line):
            continue
        if _INTERNAL.search(line):
            continue
        line = " ".join(line.split())
        if len(line) > _MAX_BULLET_CHARS:
            line = line[: _MAX_BULLET_CHARS - 1].rstrip() + "…"
        if line not in bullets:
            bullets.append(line)
        if len(bullets) == _MAX_BULLETS:
            break
    return bullets


def format_strategy(strategy: str) -> str:
    """One bullet per line, ready to store and to render as a list.

    A strategy that survives nothing (every line was internal commentary) falls back to the
    original text: showing the caregiver a wordy plan beats showing an empty card.
    """
    bullets = to_bullets(strategy)
    if not bullets:
        return (strategy or "").strip()
    return "\n".join(f"- {b}" for b in bullets)
