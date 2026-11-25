"""The time zone a caregiver's calendar uses.

- Their own setting (Preferences.timezone), when they have chosen one
- Otherwise the main zone of the state they gave in intake (caregiver address)
- A time read from email or entered without a zone is taken to be in this zone
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from app.cases.store import get_profile
from app.preferences.service import get_preferences

# Each state's main zone. States split across zones use the one most of their people live in.
STATE_TIMEZONES = {
    "AL": "America/Chicago", "AK": "America/Anchorage", "AZ": "America/Phoenix", "AR": "America/Chicago",
    "CA": "America/Los_Angeles", "CO": "America/Denver", "CT": "America/New_York", "DE": "America/New_York",
    "DC": "America/New_York", "FL": "America/New_York", "GA": "America/New_York", "HI": "Pacific/Honolulu",
    "ID": "America/Boise", "IL": "America/Chicago", "IN": "America/Indiana/Indianapolis", "IA": "America/Chicago",
    "KS": "America/Chicago", "KY": "America/New_York", "LA": "America/Chicago", "ME": "America/New_York",
    "MD": "America/New_York", "MA": "America/New_York", "MI": "America/Detroit", "MN": "America/Chicago",
    "MS": "America/Chicago", "MO": "America/Chicago", "MT": "America/Denver", "NE": "America/Chicago",
    "NV": "America/Los_Angeles", "NH": "America/New_York", "NJ": "America/New_York", "NM": "America/Denver",
    "NY": "America/New_York", "NC": "America/New_York", "ND": "America/Chicago", "OH": "America/New_York",
    "OK": "America/Chicago", "OR": "America/Los_Angeles", "PA": "America/New_York", "RI": "America/New_York",
    "SC": "America/New_York", "SD": "America/Chicago", "TN": "America/Chicago", "TX": "America/Chicago",
    "UT": "America/Denver", "VT": "America/New_York", "VA": "America/New_York", "WA": "America/Los_Angeles",
    "WV": "America/New_York", "WI": "America/Chicago", "WY": "America/Denver", "PR": "America/Puerto_Rico",
}


def valid_timezone(name: str) -> bool:
    try:
        return name in available_timezones() and ZoneInfo(name) is not None
    except (ZoneInfoNotFoundError, ValueError):
        return False


def intake_timezone(case_id: str) -> str | None:
    profile = get_profile(case_id)
    return STATE_TIMEZONES.get(profile.caregiver.state.upper()) if profile else None


def calendar_timezone(case_id: str) -> tuple[str | None, str | None]:
    """(zone, where it came from: "setting" | "intake" | None)."""
    chosen = get_preferences(case_id).timezone
    if chosen:
        return chosen, "setting"
    from_intake = intake_timezone(case_id)
    return (from_intake, "intake") if from_intake else (None, None)
