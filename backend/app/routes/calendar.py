"""Suggested events (provider-independent storage) and the calendar events accepted from
them or entered manually."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import User, get_current_user
from ..calendar_events import (
    CalendarEvent,
    _event_id_for_suggestion,
    accept_from_suggestion,
    delete_calendar_event,
    get_calendar_event,
    list_calendar_events,
)
from ..suggested_events import (
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
    # Unowned legacy suggestions remain stored, but cannot safely be assigned to a user.
    return list_suggested_events(user_id=user.id)


class SuggestedEventReview(BaseModel):
    status: Literal["pending", "accepted", "dismissed"]


@router.patch("/api/suggested-events/{event_id}")
def api_review_suggested_event(
    event_id: str,
    body: SuggestedEventReview,
    user: User = Depends(get_current_user),
) -> SuggestedEvent:
    """Persist a review decision (accept/dismiss/reset) on a suggestion.

    Accepting also materializes an idempotent calendar event; dismissing or resetting
    removes any calendar event previously accepted from this suggestion.
    """
    event = get_suggested_event(event_id)
    if event is None or event.user_id != user.id:
        raise HTTPException(status_code=404, detail="suggested event not found")
    event.status = body.status
    save_suggested_event(event)
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
