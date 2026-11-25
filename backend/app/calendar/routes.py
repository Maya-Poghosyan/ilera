"""Suggested events (provider-independent storage) and the calendar events accepted from
them or entered manually."""

from datetime import date as date_cls
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.accounts.sessions import get_current_user
from app.accounts.users import User
from app.calendar.events import (
    CalendarEvent,
    _event_id_for_suggestion,
    accept_from_suggestion,
    delete_calendar_event,
    get_calendar_event,
    list_calendar_events,
)
from app.calendar.suggestions import (
    SuggestedEvent,
    delete_suggested_event,
    get_suggested_event,
    list_suggested_events,
    save_suggested_event,
)

router = APIRouter()


@router.get("/api/suggested-events")
def api_list_suggested_events(
    user: User = Depends(get_current_user),
) -> list[SuggestedEvent]:
    return list_suggested_events(user_id=user.id)


class SuggestedEventReview(BaseModel):
    """A review decision, and/or the caregiver's corrections to a pending suggestion.

    Only the fields sent are changed. `time: null` clears the time."""
    status: Literal["pending", "accepted", "dismissed"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    date: date_cls | None = None
    time: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


@router.patch("/api/suggested-events/{event_id}")
def api_review_suggested_event(
    event_id: str,
    body: SuggestedEventReview,
    user: User = Depends(get_current_user),
) -> SuggestedEvent:
    """Persist corrections and/or a review decision (accept/dismiss/reset) on a suggestion.

    - Corrections apply to pending suggestions only; a corrected date counts as known
    - Accepting also materializes an idempotent calendar event; dismissing or resetting
      removes any calendar event previously accepted from this suggestion
    """
    event = get_suggested_event(event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status_code=404, detail="suggested event not found")
    edits = body.model_fields_set - {"status"}
    if edits and event.status != "pending":
        raise HTTPException(status_code=409, detail="only pending suggestions can be edited")
    if "title" in edits and body.title is not None:
        event.title = body.title.strip() or event.title
    if "date" in edits and body.date is not None:
        event.date, event.date_status = body.date, "known"
    if "time" in edits:
        event.time = body.time
    if body.status is None and not edits:
        raise HTTPException(status_code=422, detail="nothing to change")
    if body.status is not None:
        event.status = body.status
    if event.status == "accepted" and event.date is None:
        raise HTTPException(status_code=422, detail="add a date before accepting")
    save_suggested_event(event)
    if body.status is None:
        return event
    if body.status == "accepted":
        accept_from_suggestion(
            suggestion_id=event.id,
            user_id=user.id,
            case_id=event.case_id,
            date=event.date,
            timezone=event.timezone,
            title=event.title,
            time=event.time,
            kind=event.kind,
            description=event.description,
        )
    else:
        # A suggestion no longer accepted should not linger on the calendar.
        delete_calendar_event(_event_id_for_suggestion(event.id))
    return event


@router.delete("/api/suggested-events/{event_id}")
def api_delete_suggested_event(
    event_id: str, user: User = Depends(get_current_user)
) -> dict:
    event = get_suggested_event(event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status_code=404, detail="suggested event not found")
    # Remove any calendar event materialized from this suggestion first.
    delete_calendar_event(_event_id_for_suggestion(event_id))
    if not delete_suggested_event(event_id):
        raise HTTPException(status_code=404, detail="suggested event not found")
    return {"deleted": True}


@router.get("/api/calendar-events")
def api_list_calendar_events(
    user: User = Depends(get_current_user),
) -> list[CalendarEvent]:
    return list_calendar_events(user_id=user.id)


@router.delete("/api/calendar-events/{event_id}")
def api_delete_calendar_event(
    event_id: str, user: User = Depends(get_current_user)
) -> dict:
    event = get_calendar_event(event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status_code=404, detail="calendar event not found")
    if not delete_calendar_event(event_id):
        raise HTTPException(status_code=404, detail="calendar event not found")
    return {"deleted": True}
