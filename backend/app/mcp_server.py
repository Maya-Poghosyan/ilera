"""MCP server for Poke integration.

Exposes tools that Poke can call during conversations to create suggested
calendar events, manage reminders, and interact with the Ilera caregiver app.

Mount the SSE app at ``/mcp`` in the main FastAPI application::

    from .mcp_server import mcp
    app.mount("/mcp", mcp.sse_app())
"""

from mcp.server.fastmcp import FastMCP

from .reminders import (
    Reminder,
    ReminderKind,
    ReminderSchedule,
    ScheduleFreq,
    compute_next_run,
    delete_reminder,
    list_reminders,
    save_reminder,
)
from .suggested_events import (
    SuggestedEvent,
    delete_suggested_event,
    list_suggested_events,
    save_suggested_event,
)

mcp = FastMCP(
    "Ilera Caregiver",
    instructions=(
        "You are connected to the Ilera caregiver app. "
        "Use these tools to create calendar events from emails/messages, "
        "manage care reminders, and help caregivers stay on top of benefits."
    ),
)


@mcp.tool()
def add_suggested_event(
    day: int,
    title: str,
    description: str,
    time: str | None = None,
    kind: str = "Appointment",
) -> dict:
    """Create a suggested calendar event detected from an email or message.

    Use this when you find a medical appointment, pharmacy pickup, benefit
    deadline, or other caregiving-related event in the user's emails or
    messages. The event will appear as a suggestion on the Ilera Care Calendar.

    Args:
        day: Day of the month (1-31).
        title: Short event title (e.g. "Dr. Smith cardiology follow-up").
        description: Where it was detected and context
            (e.g. "Found in email from Kaiser — appointment confirmation for June 15").
        time: Optional time string (e.g. "2:30 PM").
        kind: Event type — one of "Appointment", "Visit", "Deadline", "Reminder".
    """
    event = SuggestedEvent(
        day=day,
        title=title,
        time=time,
        kind=kind,
        description=description,
    )
    save_suggested_event(event)
    return {"status": "created", "event_id": event.id, "title": title, "day": day}


@mcp.tool()
def get_suggested_events() -> list[dict]:
    """List all suggested calendar events currently on the Ilera Care Calendar.

    Returns the events that were detected from emails/messages and are
    waiting for the caregiver to accept or dismiss.
    """
    return [e.model_dump() for e in list_suggested_events()]


@mcp.tool()
def remove_suggested_event(event_id: str) -> dict:
    """Remove a suggested event from the calendar.

    Args:
        event_id: The ID of the suggested event to remove.
    """
    deleted = delete_suggested_event(event_id)
    return {"status": "deleted" if deleted else "not_found", "event_id": event_id}


@mcp.tool()
def get_reminders() -> list[dict]:
    """List all active care reminders configured in Ilera.

    Returns reminders for daily care logs, appointments, renewal deadlines, etc.
    """
    return [r.model_dump() for r in list_reminders()]


@mcp.tool()
def create_reminder(
    message: str,
    kind: str = "custom",
    freq: str = "daily",
    time: str = "09:00",
    weekday: int | None = None,
    date: str | None = None,
) -> dict:
    """Create a new care reminder that will be delivered via Poke.

    Args:
        message: The reminder message text.
        kind: Reminder type — "daily_care_log", "appointment",
            "renewal_deadline", or "custom".
        freq: How often — "daily", "weekly", or "once".
        time: Time to send in HH:MM 24-hour format (e.g. "09:00", "18:30").
        weekday: Day of week (0=Mon, 6=Sun). Required when freq is "weekly".
        date: ISO date (YYYY-MM-DD). Required when freq is "once".
    """
    schedule = ReminderSchedule(
        freq=ScheduleFreq(freq),
        time=time,
        weekday=weekday,
        date=date,
    )
    reminder = Reminder(
        kind=ReminderKind(kind),
        message=message,
        schedule=schedule,
        active=True,
        next_run=compute_next_run(schedule),
    )
    save_reminder(reminder)
    return {
        "status": "created",
        "reminder_id": reminder.id,
        "message": message,
        "schedule": schedule.model_dump(),
    }


@mcp.tool()
def remove_reminder(reminder_id: str) -> dict:
    """Delete a care reminder.

    Args:
        reminder_id: The ID of the reminder to delete.
    """
    deleted = delete_reminder(reminder_id)
    return {"status": "deleted" if deleted else "not_found", "reminder_id": reminder_id}
