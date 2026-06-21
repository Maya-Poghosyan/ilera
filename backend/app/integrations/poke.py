"""Poke integration — send agentic messages/reminders to the caregiver.

Poke API: POST https://poke.com/api/v1/inbound/api-message with a Bearer token.
The message is delivered into the user's Poke conversation (Apple Messages, Telegram,
WhatsApp, RCS) and processed by their assistant. Used for daily care-log reminders and
event reminders.
"""

import httpx

from ..config import get_settings

API_URL = "https://poke.com/api/v1/inbound/api-message"


def available() -> bool:
    return bool(get_settings().poke_api_key)


def send_message(message: str) -> dict:
    """Send a single instruction/reminder to the user's Poke. Raises if not configured."""
    settings = get_settings()
    if not settings.poke_api_key:
        raise RuntimeError("POKE_API_KEY not configured")
    resp = httpx.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {settings.poke_api_key}",
            "Content-Type": "application/json",
        },
        json={"message": message},
        timeout=20.0,
    )
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {"status": resp.status_code, "text": resp.text}


def daily_care_log_prompt(recipient_name: str = "your loved one") -> str:
    return (
        f"Daily Ilera check-in: How did caregiving go today for {recipient_name}? "
        "Reply with hours spent and anything notable (meals, meds, mood, incidents) "
        "and I'll log it for benefits renewal."
    )


def scan_for_events() -> dict:
    """Ask Poke to scan the user's recent messages/emails for medical or
    caregiving-related events.  Returns the raw Poke response (the caller
    decides how to surface the suggestions).
    """
    settings = get_settings()
    if not settings.poke_api_key:
        raise RuntimeError("POKE_API_KEY not configured")
    resp = httpx.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {settings.poke_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "message": (
                "Scan my recent emails and messages for anything medical or "
                "caregiving-related — appointments, prescription refills, "
                "insurance renewals, lab results, care-plan updates. "
                "For each item found, return a JSON array of objects with keys: "
                "title, date (ISO-8601 if available, otherwise descriptive), "
                "source (email subject or message preview), and kind "
                "(Appointment, Deadline, Refill, Lab, or Other)."
            ),
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {"status": resp.status_code, "text": resp.text}
