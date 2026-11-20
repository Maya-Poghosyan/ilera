"""The document-reading API contract: error codes and the suggestions returned for review."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class ErrorCode(StrEnum):
    EMPTY = "empty"
    TOO_LARGE = "too_large"
    UNSUPPORTED_TYPE = "unsupported_type"
    ENCRYPTED_PDF = "encrypted_pdf"
    TOO_MANY_PAGES = "too_many_pages"
    UNREADABLE = "unreadable"
    NO_TEXT_LAYER = "no_text_layer"
    RATE_LIMITED = "rate_limited"
    UNCONFIGURED = "unconfigured"
    EXTRACTION_FAILED = "extraction_failed"


HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.EMPTY: 400, ErrorCode.TOO_LARGE: 413, ErrorCode.UNSUPPORTED_TYPE: 415,
    ErrorCode.ENCRYPTED_PDF: 422, ErrorCode.TOO_MANY_PAGES: 422, ErrorCode.UNREADABLE: 422,
    ErrorCode.NO_TEXT_LAYER: 422, ErrorCode.RATE_LIMITED: 429, ErrorCode.UNCONFIGURED: 503,
    ErrorCode.EXTRACTION_FAILED: 502,
}


class DocumentError(Exception):
    """A fixed, user-safe code. Never carries document content."""

    def __init__(self, code: ErrorCode):
        super().__init__(code.value)
        self.code = code


HouseholdPerson = Literal["caregiver", "recipient", "spouse", "other_household_member"]


class Source(BaseModel):
    page: int = Field(ge=1)
    evidence: str
    as_of: str | None


class AnswerSuggestion(BaseModel):
    """A proposed value for one intake question, already valid for that question."""
    kind: Literal["answer"] = "answer"
    field_id: str
    value: str | int | float | bool | list[str]
    tax_year: int | None = None
    source: Source

    @model_validator(mode="after")
    def tax_year_only_on_tax_answers(self):
        if self.tax_year is not None and not self.field_id.startswith("tax."):
            raise ValueError("tax_year applies only to tax answers")
        return self


class IncomeSuggestion(BaseModel):
    """Gross monthly income for one household-roster member."""
    kind: Literal["member_income"] = "member_income"
    person: HouseholdPerson
    monthly_amount: float = Field(ge=0)
    source: Source


Suggestion = Annotated[AnswerSuggestion | IncomeSuggestion, Field(discriminator="kind")]


class DocumentReading(BaseModel):
    suggestions: list[Suggestion]
