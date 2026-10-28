"""Caregiver preferences."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..access import require_case_access
from ..preferences import Preferences, get_preferences, save_preferences

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
