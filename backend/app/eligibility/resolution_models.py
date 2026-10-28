"""Serializable screening-resolution contracts, independent of the evaluator."""
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


ResolutionCategory = Literal["financial", "coverage", "medical", "household", "employment", "general"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GuidanceResource(StrictModel):
    resource_id: str = Field(min_length=1)
    kind: Literal["portal", "form", "document", "contact", "instructions"]
    title: str = Field(min_length=1)
    url: HttpUrl | None = None
    phone: str | None = None
    instructions: list[str] = Field(default_factory=list)
    source_url: HttpUrl
    checked_on: date

    @model_validator(mode="after")
    def require_destination(self):
        if not (self.url or self.phone or self.instructions):
            raise ValueError("Resource must provide a destination or instructions")
        return self


class ResolutionMethod(StrictModel):
    kind: Literal["manual_entry", "targeted_question", "document_upload"]
    label: str = Field(min_length=1)


class ResolutionTemplate(StrictModel):
    template_id: str = Field(min_length=1)
    category: ResolutionCategory = "general"
    profile_path: str
    title: str = Field(min_length=1)
    description: str = ""
    guided_steps: list[str] = Field(default_factory=list)
    resources: list[GuidanceResource] = Field(default_factory=list)
    acceptable_evidence_types: list[str] = Field(default_factory=list)
    methods: list[ResolutionMethod] = Field(default_factory=lambda: [ResolutionMethod(kind="manual_entry", label="Enter information")])
    status: Literal["draft", "reviewed"] = "draft"

    @model_validator(mode="after")
    def validate_binding(self):
        from .facts import fact_registry
        if self.profile_path not in fact_registry():
            raise ValueError("Template must bind to a persistent canonical fact")
        kinds = [m.kind for m in self.methods]
        if not kinds or len(kinds) != len(set(kinds)):
            raise ValueError("Methods must be nonempty and unique")
        # Upload extraction is a later adapter, not a working completion method yet.
        if "document_upload" in kinds:
            raise ValueError("Document uploads require an implemented evidence adapter")
        return self


class ResolutionTask(StrictModel):
    id: str
    case_id: str
    profile_path: str
    category: ResolutionCategory = "general"
    primary_program_id: str
    related_program_ids: list[str] = Field(default_factory=list)
    criterion_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    title: str
    description: str
    guided_steps: list[str]
    resources: list[GuidanceResource] = Field(default_factory=list)
    acceptable_evidence_types: list[str] = Field(default_factory=list)
    methods: list[ResolutionMethod]
    input_schema: dict[str, Any]
    template_id: str | None = None
    state: Literal["available", "deferred", "resolved", "superseded"] = "available"
    completed_at: str | None = None
    reopen_reason: str | None = None


class CompletionRequest(StrictModel):
    idempotency_key: str = Field(min_length=1, max_length=200)
    expected_fact_revision: int = Field(ge=0)
    expected_task_revision: int = Field(ge=0)
    method: Literal["manual_entry", "targeted_question"] = "manual_entry"
    value: Any


class CompletionReceipt(StrictModel):
    task_id: str
    request_digest: str
    fact_revision: int


class ResolutionState(StrictModel):
    revision: int = 0
    tasks: dict[str, ResolutionTask] = Field(default_factory=dict)
    receipts: dict[str, CompletionReceipt] = Field(default_factory=dict)
