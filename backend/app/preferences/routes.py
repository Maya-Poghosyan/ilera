"""Caregiver preferences."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.accounts.access import require_case_access
from app.calendar.timezones import calendar_timezone, valid_timezone
from app.preferences.service import Preferences, get_preferences, save_preferences

router = APIRouter()


@router.get("/api/preferences/{case_id}")
def api_get_preferences(case_id: str, _: str = Depends(require_case_access)) -> Preferences:
    return get_preferences(case_id)


class PreferencesUpdate(BaseModel):
    monitor_inboxes: bool


@router.put("/api/preferences/{case_id}")
def api_set_preferences(
    case_id: str, body: PreferencesUpdate, _: str = Depends(require_case_access)
) -> Preferences:
    prefs = get_preferences(case_id)
    prefs.monitor_inboxes = body.monitor_inboxes
    prefs.monitor_inboxes_updated_at = datetime.now(timezone.utc).isoformat()
    return save_preferences(prefs)


class CalendarTimezone(BaseModel):
    timezone: str | None
    source: str | None  # "setting" | "intake" | None


@router.get("/api/preferences/{case_id}/timezone")
def api_get_timezone(case_id: str, _: str = Depends(require_case_access)) -> CalendarTimezone:
    zone, source = calendar_timezone(case_id)
    return CalendarTimezone(timezone=zone, source=source)


class TimezoneUpdate(BaseModel):
    timezone: str


@router.put("/api/preferences/{case_id}/timezone")
def api_set_timezone(case_id: str, body: TimezoneUpdate, _: str = Depends(require_case_access)) -> CalendarTimezone:
    if not valid_timezone(body.timezone):
        raise HTTPException(status_code=422, detail="unknown time zone")
    prefs = get_preferences(case_id)
    prefs.timezone = body.timezone
    save_preferences(prefs)
    return CalendarTimezone(timezone=body.timezone, source="setting")
