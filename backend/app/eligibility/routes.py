"""Backend contract for screening tasks; application tasks are separate."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from ..access import require_case_access
from ..store import get_profile, mutate_profile
from .engine import ProgramEvaluation
from .loader import list_policies
from .resolution import (ResolutionConflict, complete_resolution, defer_resolution,
                         load_templates, refresh_resolution)
from .resolution_models import CompletionRequest, ResolutionTask, StrictModel

router = APIRouter(prefix="/api/eligibility-resolution", tags=["eligibility resolution"])


class ResolutionResponse(StrictModel):
    case_id: str
    fact_revision: int
    task_revision: int
    evaluations: list[ProgramEvaluation]
    tasks: list[ResolutionTask]
    policy_coverage: list[str]


class DeferRequest(StrictModel):
    expected_task_revision: int = Field(ge=0)


def _response(profile, evaluations, policies, program_id=None):
    tasks = [task for task in profile.resolution.tasks.values()
             if program_id is None or program_id in [task.primary_program_id, *task.related_program_ids]]
    order = {"available": 0, "deferred": 1, "resolved": 2, "superseded": 3}
    tasks.sort(key=lambda task: (order[task.state], -len(task.related_program_ids), task.id))
    return ResolutionResponse(case_id=profile.id, fact_revision=profile.fact_revision,
                              task_revision=profile.resolution.revision,
                              evaluations=[e for e in evaluations if program_id is None or e.program_id == program_id],
                              tasks=tasks, policy_coverage=sorted(p.program_id for p in policies))


def _run(case_id, operation):
    try:
        return mutate_profile(case_id, operation)
    except KeyError:
        raise HTTPException(404, "case or task not found") from None
    except ResolutionConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except ValueError:
        # Pydantic exceptions can include submitted values; don't echo case facts.
        raise HTTPException(422, "Invalid resolution result or configuration") from None


@router.post("/{case_id}/refresh", response_model=ResolutionResponse)
def refresh(case_id: str, _: str = Depends(require_case_access)):
    policies, templates = list_policies(), load_templates()
    def operation(profile):
        updated, evaluations = refresh_resolution(profile, policies, templates)
        return updated, _response(updated, evaluations, policies)
    return _run(case_id, operation)


@router.get("/{case_id}", response_model=ResolutionResponse)
def read(case_id: str, program_id: str | None = None, _: str = Depends(require_case_access)):
    profile = get_profile(case_id)
    if profile is None:
        raise HTTPException(404, "case not found")
    policies, templates = list_policies(), load_templates()
    updated, evaluations = refresh_resolution(profile, policies, templates)
    return _response(updated, evaluations, policies, program_id)


@router.post("/{case_id}/tasks/{task_id}/result", response_model=ResolutionResponse)
def complete(case_id: str, task_id: str, body: CompletionRequest, _: str = Depends(require_case_access)):
    policies, templates = list_policies(), load_templates()
    def operation(profile):
        updated, evaluations = complete_resolution(profile, task_id, body, policies, templates)
        return updated, _response(updated, evaluations, policies)
    return _run(case_id, operation)


@router.post("/{case_id}/tasks/{task_id}/defer", response_model=ResolutionResponse)
def defer(case_id: str, task_id: str, body: DeferRequest, _: str = Depends(require_case_access)):
    policies, templates = list_policies(), load_templates()
    def operation(profile):
        current, _ = refresh_resolution(profile, policies, templates)
        updated = defer_resolution(current, task_id, body.expected_task_revision)
        updated, evaluations = refresh_resolution(updated, policies, templates)
        return updated, _response(updated, evaluations, policies)
    return _run(case_id, operation)
