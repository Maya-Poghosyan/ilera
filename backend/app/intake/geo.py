"""ZIP -> county resolution.

Many caregiver programs are administered at the county level (IHSS county social
services, Medi-Cal county offices, Regional Centers, PACE service areas, Area
Agencies on Aging), so eligibility routing and next-step guidance depend on the
recipient's county, not just their state. This resolves a ZIP (optionally
constrained by state) to a county name, using the offline ``zipcodes`` dataset.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

try:
    import zipcodes as _zipcodes
except Exception:  # pragma: no cover - dependency optional at runtime
    _zipcodes = None


def normalize_county(value: object) -> str:
    """Bare county name, so typed answers and ZIP lookups agree on one spelling."""
    text = " ".join(str(value or "").split())
    for suffix in (" County", " Parish", " Borough"):
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


@lru_cache(maxsize=4096)
def zip_to_county(zip_code: str, state: str = "") -> Optional[str]:
    """Return the county name for a 5-digit ZIP, or None if unknown.

    ``state`` (two-letter) disambiguates the rare ZIP shared across states.
    """
    if not zip_code or _zipcodes is None:
        return None
    z = str(zip_code).strip()[:5]
    if not (len(z) == 5 and z.isdigit()):
        return None
    try:
        matches = _zipcodes.matching(z)
    except Exception:
        return None
    if not matches:
        return None
    if state:
        st = state.strip().upper()
        matches = [m for m in matches if m.get("state", "").upper() == st] or matches
    return matches[0].get("county") or None
