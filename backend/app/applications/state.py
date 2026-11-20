"""Per-case application state: status, answers and the questions asked so far."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core import db


class AppStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    needs_info = "needs_info"
    completed = "completed"


class AppQuestion(BaseModel):
    """A single question shown one-by-one on the frontend.

    The top-level fields (``field_id``, ``text``, ``type``, ``required``, ``options``,
    ``why_this_matters``) are the intake ``QuestionField`` shape, so the frontend renders
    these directly with no adapter. The remaining fields are backend-only metadata used to
    translate the user's answer back into concrete PDF values at fill time (and, later, to
    feed the specialist layer).
    """

    field_id: str
    text: str
    type: str = "short_text"
    required: bool = True
    options: list[str] = Field(default_factory=list)
    why_this_matters: str = ""

    # backend-only
    form_id: str = ""
    fields: list[str] = Field(default_factory=list)
    option_values: dict[str, str] = Field(default_factory=dict)  # option label -> raw PDF value
    interpret: bool = False

    # Questions sharing a ``group_id`` are one screen: a group asks for one real-world
    # fact and each of its inputs fills different boxes, so they are answered together.
    group_id: str = ""
    group_prompt: str = ""
    input: str = ""
    option_fields: dict[str, list[str]] = Field(default_factory=dict)
    # A "if yes, ..." follow-up: only shown once an earlier answer satisfies this, e.g.
    # `past_ihss.received_ihss_before == "Yes"`. Conditions the profile can settle are
    # applied here instead, and the group never reaches the frontend at all.
    ask_when: str = ""


class ApplicationState(BaseModel):
    case_id: str
    program: str
    status: AppStatus = AppStatus.open
    answers: dict[str, Any] = Field(default_factory=dict)
    questions: list[AppQuestion] = Field(default_factory=list)


_store = db.JsonStore("applications", keys=("case_id", "program"))


def _slug(program: str) -> str:
    return program.lower().replace(" ", "_").replace("/", "_")


def save_app_state(state: ApplicationState) -> None:
    _store.put((state.case_id, _slug(state.program)), state.model_dump_json())


def get_app_state(case_id: str, program: str) -> Optional[ApplicationState]:
    doc = _store.get((case_id, _slug(program)))
    return ApplicationState.model_validate(doc) if doc else None


def list_app_states(case_id: str) -> list[ApplicationState]:
    return [ApplicationState.model_validate(doc) for doc in _store.list(case_id)]
