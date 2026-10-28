from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import router as auth_router
from .config import get_settings
from .eligibility.routes import router as eligibility_resolution_router
from .email_ingestion.notifications import router as email_notifications_router
from .email_ingestion.privacy import configure_email_access_logging
from .email_ingestion.routes import router as email_router
from .routes import ROUTERS

settings = get_settings()

# Scheduled work (e.g. the unclaimed-case purge) runs as Container Apps Jobs from app/jobs,
# not in this process, so scaling out replicas never multiplies it.
app = FastAPI(title=settings.app_name)
configure_email_access_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Order matters where paths overlap: these are registered ahead of the area routers.
app.include_router(auth_router)
app.include_router(eligibility_resolution_router)
app.include_router(email_router)
app.include_router(email_notifications_router)
for router in ROUTERS:
    app.include_router(router)
