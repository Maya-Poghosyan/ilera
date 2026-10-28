"""Availability is separate from a profile value, including its model default."""
from typing import Literal

from pydantic import BaseModel


class FactMetadata(BaseModel):
    availability: Literal["known", "unknown", "skipped", "unavailable", "conflicting"]
    source_kind: Literal["user_report", "document", "agency_record", "derived"]
    source_ref: str | None = None
    updated_at: str
    revision: int
    precision: Literal["exact", "bucket", "derived"] = "exact"
