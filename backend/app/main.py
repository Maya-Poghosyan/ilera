from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import health
from app.accounts import auth
from app.applications import routes as applications
from app.calendar import routes as calendar
from app.cases import routes as cases
from app.core.config import get_settings
from app.eligibility import routes as eligibility
from app.email_ingestion import notifications as email_notifications
from app.email_ingestion import routes as email
from app.email_ingestion.privacy import configure_email_access_logging
from app.forms import routes as forms
from app.intake import documents as intake_documents
from app.preferences import routes as preferences
from app.records import routes as records
from app.reference_guides import routes as reference_guides
from app.reminders import routes as reminders

settings = get_settings()

# Scheduled work (e.g. the unclaimed-case purge) runs as Container Apps Jobs,
# not in this process, so scaling out replicas never multiplies it.
# No /docs, /redoc or /openapi.json: the API is public and scanners probe it constantly.
app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None, openapi_url=None)
configure_email_access_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Order matters where paths overlap (e.g. /api/reminders/templates before /api/reminders/{id}).
for feature in (auth, eligibility, email, email_notifications, intake_documents, health, cases, forms,
                reference_guides, reminders, applications, preferences, calendar, records):
    app.include_router(feature.router)
