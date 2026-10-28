"""Reminder CRUD (delivery is not configured)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..access import authorize_case
from ..auth import User, get_optional_user
from ..reminders import (
    TEMPLATES,
    Reminder,
    ReminderKind,
    ReminderSchedule,
    compute_next_run,
    delete_reminder,
    get_reminder,
    list_reminders,
    save_reminder,
)
from ..store import get_case_id_for_user

router = APIRouter()


class ReminderCreate(BaseModel):
    case_id: Optional[str] = None
    kind: ReminderKind = ReminderKind.custom
    message: str = ""
    schedule: ReminderSchedule = ReminderSchedule()
    active: bool = True


class ReminderUpdate(BaseModel):
    message: Optional[str] = None
    schedule: Optional[ReminderSchedule] = None
    active: Optional[bool] = None
    kind: Optional[ReminderKind] = None


@router.get("/api/reminders")
def api_list_reminders(case_id: Optional[str] = None, user: Optional[User] = Depends(get_optional_user)) -> list[Reminder]:
    scope = case_id or (get_case_id_for_user(user.id) if user else None)
    if not scope:
        return []
    authorize_case(scope, user)
    return [r for r in list_reminders() if r.case_id == scope]


@router.post("/api/reminders", status_code=201)
def api_create_reminder(
    body: ReminderCreate, user: Optional[User] = Depends(get_optional_user)
) -> Reminder:
    scope = body.case_id or (get_case_id_for_user(user.id) if user else None)
    if not scope:
        raise HTTPException(status_code=422, detail="A case is required")
    authorize_case(scope, user)
    reminder = Reminder(
        case_id=scope,
        kind=body.kind,
        message=body.message,
        schedule=body.schedule,
        active=body.active,
    )
    reminder.next_run = compute_next_run(reminder.schedule)
    save_reminder(reminder)
    return reminder


@router.get("/api/reminders/templates")
def api_templates() -> dict:
    return TEMPLATES


@router.get("/api/reminders/{reminder_id}")
def api_get_reminder(reminder_id: str, user: Optional[User] = Depends(get_optional_user)) -> Reminder:
    r = get_reminder(reminder_id)
    if r is None or not r.case_id:
        raise HTTPException(status_code=404, detail="reminder not found")
    authorize_case(r.case_id, user)
    return r


@router.patch("/api/reminders/{reminder_id}")
def api_patch_reminder(reminder_id: str, body: ReminderUpdate, user: Optional[User] = Depends(get_optional_user)) -> Reminder:
    r = get_reminder(reminder_id)
    if r is None or not r.case_id:
        raise HTTPException(status_code=404, detail="reminder not found")
    authorize_case(r.case_id, user)
    if body.message is not None:
        r.message = body.message
    if body.schedule is not None:
        r.schedule = body.schedule
        r.next_run = compute_next_run(r.schedule)
    if body.active is not None:
        r.active = body.active
        if r.active and r.next_run is None:
            r.next_run = compute_next_run(r.schedule)
    if body.kind is not None:
        r.kind = body.kind
    save_reminder(r)
    return r


@router.delete("/api/reminders/{reminder_id}")
def api_delete_reminder(reminder_id: str, user: Optional[User] = Depends(get_optional_user)) -> dict:
    api_get_reminder(reminder_id, user)
    if not delete_reminder(reminder_id):
        raise HTTPException(status_code=404, detail="reminder not found")
    return {"deleted": True}
