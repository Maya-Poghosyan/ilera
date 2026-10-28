"""Records & renewal: timekeeping, journal (with fall detection), and renewal items."""

from datetime import date as Date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from ..access import authorize_case, require_case_access
from ..auth import User, get_optional_user
from ..records import (
    JournalEntry,
    RenewalItem,
    TimekeepingEntry,
    _detect_fall,
    delete_journal,
    delete_renewal_item,
    delete_timekeeping,
    get_journal,
    get_renewal_item,
    get_timekeeping,
    list_journal,
    list_renewal_items,
    list_timekeeping,
    save_journal,
    save_renewal_item,
    save_timekeeping,
)

router = APIRouter()


class TimekeepingCreate(BaseModel):
    case_id: str
    date: str
    hours: float = Field(gt=0, le=24, allow_inf_nan=False)
    start_time: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    service_type: Literal["personal_care", "domestic", "paramedical", "accompaniment"] = "personal_care"
    tasks: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        if Date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use YYYY-MM-DD")
        return value

    @model_validator(mode="after")
    def valid_duration(self):
        if bool(self.start_time) != bool(self.end_time):
            raise ValueError("Provide both start and end times")
        if self.start_time and self.end_time:
            start = sum(int(v) * m for v, m in zip(self.start_time.split(":"), (60, 1)))
            end = sum(int(v) * m for v, m in zip(self.end_time.split(":"), (60, 1)))
            if end <= start or abs(self.hours * 60 - (end - start)) > 0.01:
                raise ValueError("Hours must match the same-day time range; split overnight care into separate dates")
        return self


class JournalCreate(BaseModel):
    case_id: str
    date: str
    text: str = Field(min_length=1, max_length=20000)

    _valid_date = field_validator("date")(TimekeepingCreate.valid_date.__func__)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a journal note")
        return value.strip()


class IncidentReview(BaseModel):
    status: Literal["confirmed", "dismissed", "unreviewed"]


class RenewalItemCreate(BaseModel):
    case_id: str
    program: str = Field(default="IHSS", min_length=1, max_length=120)
    due_date: Optional[str] = None
    status: Literal["active", "pending", "overdue"] = "active"
    notes: str = Field(default="", max_length=2000)
    last_completed_date: Optional[str] = None
    renewal_period_months: Optional[int] = Field(default=None, ge=1, le=120)

    @field_validator("due_date", "last_completed_date")
    @classmethod
    def valid_optional_date(cls, value):
        return TimekeepingCreate.valid_date(value) if value is not None else None


class RenewalItemUpdate(BaseModel):
    program: Optional[str] = Field(default=None, min_length=1, max_length=120)
    due_date: Optional[str] = None
    status: Optional[Literal["active", "pending", "overdue"]] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    last_completed_date: Optional[str] = None
    renewal_period_months: Optional[int] = Field(default=None, ge=1, le=120)

    @field_validator("due_date", "last_completed_date")
    @classmethod
    def valid_optional_date(cls, value):
        return TimekeepingCreate.valid_date(value) if value is not None else None


@router.get("/api/records/timekeeping/{case_id}")
def api_list_timekeeping(
    case_id: str, _: str = Depends(require_case_access)
) -> list[TimekeepingEntry]:
    return list_timekeeping(case_id)


@router.post("/api/records/timekeeping", status_code=201)
def api_create_timekeeping(
    body: TimekeepingCreate, user: Optional[User] = Depends(get_optional_user)
) -> TimekeepingEntry:
    authorize_case(body.case_id, user)
    entry = TimekeepingEntry(
        case_id=body.case_id,
        date=body.date,
        hours=body.hours,
        start_time=body.start_time,
        end_time=body.end_time,
        service_type=body.service_type,
        tasks=body.tasks,
        notes=body.notes,
    )
    save_timekeeping(entry)
    return entry


@router.delete("/api/records/timekeeping/{entry_id}")
def api_delete_timekeeping(
    entry_id: str, case_id: str, _: str = Depends(require_case_access)
) -> dict:
    if not delete_timekeeping(entry_id, case_id):
        raise HTTPException(status_code=404, detail="timekeeping entry not found")
    return {"deleted": True}


@router.get("/api/records/journal/{case_id}")
def api_list_journal(
    case_id: str, _: str = Depends(require_case_access)
) -> list[JournalEntry]:
    return list_journal(case_id)


@router.post("/api/records/journal", status_code=201)
def api_create_journal(
    body: JournalCreate, user: Optional[User] = Depends(get_optional_user)
) -> JournalEntry:
    authorize_case(body.case_id, user)
    entry = JournalEntry(
        case_id=body.case_id,
        date=body.date,
        text=body.text,
        fall_flagged=_detect_fall(body.text),
    )
    save_journal(entry)
    return entry


@router.delete("/api/records/journal/{entry_id}")
def api_delete_journal(
    entry_id: str, case_id: str, _: str = Depends(require_case_access)
) -> dict:
    if not delete_journal(entry_id, case_id):
        raise HTTPException(status_code=404, detail="journal entry not found")
    return {"deleted": True}


@router.get("/api/records/renewals/{case_id}")
def api_list_renewals(
    case_id: str, _: str = Depends(require_case_access)
) -> list[RenewalItem]:
    return list_renewal_items(case_id)


@router.post("/api/records/renewals", status_code=201)
def api_create_renewal_item(
    body: RenewalItemCreate, user: Optional[User] = Depends(get_optional_user)
) -> RenewalItem:
    authorize_case(body.case_id, user)
    item = RenewalItem(
        case_id=body.case_id,
        program=body.program,
        due_date=body.due_date,
        status=body.status,
        notes=body.notes,
        last_completed_date=body.last_completed_date,
        renewal_period_months=body.renewal_period_months,
    )
    save_renewal_item(item)
    return item


@router.put("/api/records/renewals/{item_id}")
def api_update_renewal_item(
    item_id: str,
    body: RenewalItemUpdate,
    case_id: str,
    _: str = Depends(require_case_access),
) -> RenewalItem:
    existing = get_renewal_item(case_id, item_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="renewal not found")
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(existing, field, value)
    save_renewal_item(existing)
    return existing


@router.delete("/api/records/renewals/{item_id}")
def api_delete_renewal_item(
    item_id: str, case_id: str, _: str = Depends(require_case_access)
) -> dict:
    if not delete_renewal_item(case_id, item_id):
        raise HTTPException(status_code=404, detail="renewal not found")
    return {"deleted": True}


@router.get("/api/records/{case_id}")
def api_records_summary(case_id: str, _: str = Depends(require_case_access)) -> dict:
    """Combined summary: timekeeping + journal + renewals + fall_flag."""
    timekeeping = list_timekeeping(case_id)
    journal = list_journal(case_id)
    renewals = list_renewal_items(case_id)
    fall_flag = any(j.fall_flagged and j.incident_status != "dismissed" for j in journal)
    return {
        "timekeeping": timekeeping,
        "journal": journal,
        "renewals": renewals,
        "fall_flag": fall_flag,
    }


@router.put("/api/records/timekeeping/{entry_id}")
def api_update_timekeeping(entry_id: str, body: TimekeepingCreate, user: Optional[User] = Depends(get_optional_user)) -> TimekeepingEntry:
    authorize_case(body.case_id, user)
    existing = get_timekeeping(entry_id, body.case_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="timekeeping entry not found")
    entry = TimekeepingEntry(**body.model_dump(), id=existing.id, created_at=existing.created_at)
    save_timekeeping(entry)
    return entry


@router.put("/api/records/journal/{entry_id}")
def api_update_journal(entry_id: str, body: JournalCreate, user: Optional[User] = Depends(get_optional_user)) -> JournalEntry:
    authorize_case(body.case_id, user)
    existing = get_journal(entry_id, body.case_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="journal entry not found")
    entry = JournalEntry(**body.model_dump(), id=existing.id, created_at=existing.created_at,
                         fall_flagged=_detect_fall(body.text),
                         incident_status=existing.incident_status if body.text == existing.text else "unreviewed")
    save_journal(entry)
    return entry


@router.patch("/api/records/journal/{entry_id}/incident")
def api_review_incident(entry_id: str, body: IncidentReview, case_id: str, _: str = Depends(require_case_access)) -> JournalEntry:
    entry = get_journal(entry_id, case_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="journal entry not found")
    entry.incident_status = body.status
    save_journal(entry)
    return entry
