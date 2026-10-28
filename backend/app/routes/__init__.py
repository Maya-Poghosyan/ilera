"""HTTP routers for the API, one module per area. `app.main` includes them in the order
listed here; order matters where paths overlap (e.g. /api/reminders/templates must be
registered before /api/reminders/{reminder_id})."""

from . import applications, calendar, cases, forms, health, preferences, rag, records, reference_guides, reminders

ROUTERS = [
    health.router,
    cases.router,
    rag.router,
    forms.router,
    reference_guides.router,
    reminders.router,
    applications.router,
    preferences.router,
    calendar.router,
    records.router,
]
