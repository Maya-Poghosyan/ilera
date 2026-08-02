"""MCP server for Poke integration.

Exposes tools that Poke can call during conversations to create suggested
calendar events, manage reminders, and interact with the Ilera caregiver app.

Mount the SSE app at ``/mcp`` in the main FastAPI application::

    from .mcp_server import build_mcp_app
    app.mount("/mcp", build_mcp_app())

Poke reaches this over the public internet, so ``MCP_API_KEY`` gates every
request. Poke sends the integration's API key as ``Authorization: Bearer ...``.
"""

import hmac
import logging

from mcp.server.fastmcp import FastMCP
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import get_settings
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


logger = logging.getLogger(__name__)


class BearerTokenMiddleware:
    """Reject requests whose bearer token doesn't match the configured key."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        header = dict(scope["headers"]).get(b"authorization", b"").decode()
        presented = header[7:] if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(presented, self.token):
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"text/plain")],
                }
            )
            await send({"type": "http.response.body", "body": b"unauthorized"})
            return
        await self.app(scope, receive, send)


def build_mcp_app() -> ASGIApp:
    """The MCP SSE app, wrapped in bearer auth when ``MCP_API_KEY`` is set."""
    app = mcp.sse_app()
    token = get_settings().mcp_api_key
    if not token:
        logger.warning(
            "MCP_API_KEY is not set — the MCP server is unauthenticated. "
            "Set it before exposing this app publicly."
        )
        return app
    return BearerTokenMiddleware(app, token)


@mcp.tool()
def add_suggested_event(
    date: str,
    title: str,
    description: str,
    time: str | None = None,
    kind: str = "Appointment",
) -> dict:
    """File a caregiving event you found in the user's email, messages or calendar.

    Call this once per event, as soon as you find one — medical appointments,
    pharmacy pickups and refills, lab results, insurance or benefit renewal
    deadlines, paperwork due dates, home visits. It is the only way to get an
    event onto the Ilera Care Calendar; describing it in chat does nothing.
    Call `get_suggested_events` first and skip anything already filed.

    Args:
        date: Calendar date as ISO 8601 YYYY-MM-DD (e.g. "2026-06-15"). Resolve
            relative dates like "next Tuesday" against today before calling.
        title: Short event title (e.g. "Dr. Smith cardiology follow-up").
        description: Where it was detected and context
            (e.g. "Found in email from Kaiser — appointment confirmation for June 15").
        time: Optional time of day (e.g. "2:30 PM").
        kind: Event type — one of "Appointment", "Visit", "Deadline", "Reminder".
    """
    event = SuggestedEvent(
        date=date,
        title=title,
        time=time,
        kind=kind,
        description=description,
    )
    save_suggested_event(event)
    return {"status": "created", "event_id": event.id, "title": title, "date": date}


@mcp.tool()
def get_suggested_events() -> list[dict]:
    """List the events already filed on the Ilera Care Calendar.

    Check this before calling `add_suggested_event` so you don't file the same
    appointment or deadline twice.
    """
    return [e.model_dump(mode="json") for e in list_suggested_events()]


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
