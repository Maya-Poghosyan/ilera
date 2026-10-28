"""Validated policy metadata and application-controlled retrieval boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

STATES = frozenset("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY AS GU MP PR VI".split())


def today() -> date:
    return datetime.now(timezone.utc).date()


def normalize_state(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().upper()
    if value not in STATES:
        raise ValueError("State must be a US state or territory abbreviation.")
    return value


@dataclass(frozen=True)
class RetrievalScope:
    program: str
    state: str | None
    as_of: date

    def __post_init__(self) -> None:
        if not self.program.strip():
            raise ValueError("A program is required for policy retrieval.")
        object.__setattr__(self, "state", normalize_state(self.state))
        if not isinstance(self.as_of, date) or isinstance(self.as_of, datetime):
            raise ValueError("as_of must be a date.")

    @property
    def jurisdictions(self) -> list[str]:
        return ["US", self.state] if self.state else ["US"]


@dataclass(frozen=True)
class PolicyMetadata:
    applicable_programs: tuple[str, ...] = ()
    jurisdictions: tuple[str, ...] = ()
    effective_from: date | None = None
    effective_to: date | None = None  # exclusive end date
    authority_level: str = ""
    version: str = ""

    @classmethod
    def from_dict(cls, meta: dict[str, Any], program: str) -> PolicyMetadata:
        def strings(key: str, default: list[str]) -> tuple[str, ...]:
            values = meta.get(key, default)
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError(f"{key} must be an array of nonempty strings.")
            return tuple(dict.fromkeys(values))

        programs = strings("applicable_programs", [program])
        if program not in programs:
            raise ValueError("applicable_programs must include the document's primary program.")
        jurisdictions = strings("jurisdictions", [])
        if any(j != "US" and j not in STATES for j in jurisdictions):
            raise ValueError("Jurisdictions must be US or state/territory abbreviations.")
        start = date.fromisoformat(meta["effective_from"]) if meta.get("effective_from") else None
        end = date.fromisoformat(meta["effective_to"]) if meta.get("effective_to") else None
        if end and start and end <= start:
            raise ValueError("effective_to must be later than effective_from (exclusive end).")
        return cls(programs, jurisdictions, start, end,
                   str(meta.get("authority_level") or ""), str(meta.get("version") or ""))

    def allows(self, scope: RetrievalScope) -> bool:
        return (scope.program in self.applicable_programs
                and bool(set(scope.jurisdictions).intersection(self.jurisdictions))
                and (self.effective_from is None or self.effective_from <= scope.as_of)
                and (self.effective_to is None or scope.as_of < self.effective_to))

    def evidence(self) -> dict[str, Any]:
        return {"applicable_programs": list(self.applicable_programs),
                "jurisdictions": list(self.jurisdictions),
                "effective_from": self.effective_from.isoformat() if self.effective_from else None,
                "effective_to": self.effective_to.isoformat() if self.effective_to else None,
                "authority_level": self.authority_level, "version": self.version,
                "date_status": "unverified" if self.effective_from is None else "dated"}


def profile_scope(profile, program: str, *, as_of: date | None = None) -> RetrievalScope:
    """Use explicit intake location; Pydantic's default CA is not location evidence.

    State benefits use recipient residence; employment/tax research uses caregiver
    residence. Cross-state employment jurisdiction may require additional intake facts.
    Unknown location permits federal sources only.
    """
    answers = profile.answers
    caregiver_state = answers.get("caregiver.address.state")
    recipient_state = answers.get("recipient.address.state")
    if answers.get("caregiver.coresidence") == "Yes":
        recipient_state = caregiver_state
    caregiver_program = program in {"pfl", "tax"}
    path = "caregiver.state" if caregiver_program else "care_recipient.state"
    metadata = profile.fact_metadata.get(path)
    if metadata:
        state = (profile.caregiver.state if caregiver_program else profile.care_recipient.state) if metadata.availability == "known" else None
    else:
        state = caregiver_state if caregiver_program else recipient_state
    return RetrievalScope(program, state or None, as_of or today())
