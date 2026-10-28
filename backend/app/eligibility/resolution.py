"""One task per missing fact; reviewed guidance is independently replaceable content.

All mutations return a copy. A caller must persist the returned case atomically;
validation/re-evaluation failures never partially mutate the original case.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pydantic import TypeAdapter

from ..models import CaseProfile
from .engine import ProgramEvaluation, evaluate_program
from .facts import fact_registry, known_fact, write_fact
from .policy import ProgramPolicy
from .resolution_models import (CompletionReceipt, CompletionRequest, ResolutionMethod,
                                ResolutionTask, ResolutionTemplate)

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "data" / "resolution_templates"


class ResolutionConflict(ValueError):
    pass


def load_templates() -> list[ResolutionTemplate]:
    templates = [ResolutionTemplate.model_validate_json(p.read_text())
                 for p in sorted(_TEMPLATE_DIR.glob("*.json"))]
    reviewed = [t for t in templates if t.status == "reviewed"]
    if len({t.profile_path for t in reviewed}) != len(reviewed):
        raise ValueError("Only one reviewed template per fact is allowed")
    return reviewed


def refresh_resolution(profile: CaseProfile, policies: list[ProgramPolicy],
                       templates: list[ResolutionTemplate] | None = None
                       ) -> tuple[CaseProfile, list[ProgramEvaluation]]:
    updated = profile.model_copy(deep=True)
    evaluations = [evaluate_program(updated, policy) for policy in policies]
    reviewed = [t for t in (load_templates() if templates is None else templates) if t.status == "reviewed"]
    if len({t.profile_path for t in reviewed}) != len(reviewed):
        raise ValueError("Duplicate reviewed fact templates")
    by_path = {t.profile_path: t for t in reviewed}
    external_ids = {(p.program_id, c.criterion_id) for p in policies for c in p.all_criteria() if c.kind == "external"}
    obligations: dict[str, dict] = {}
    for evaluation in evaluations:
        for pathway in evaluation.pathways:
            if pathway.state == "eliminated":
                continue
            for criterion in pathway.criteria:
                if ((evaluation.program_id, criterion.criterion_id) in external_ids
                        or criterion.criterion_id not in evaluation.unresolved_criteria
                        or criterion.resolution_kind != "user_fact"):
                    continue
                for path in criterion.required_fact_paths:
                    entry = obligations.setdefault(path, {"programs": set(), "criteria": set(), "reasons": set()})
                    entry["programs"].add(evaluation.program_id)
                    entry["criteria"].add(criterion.criterion_id)
                    metadata = updated.fact_metadata.get(path)
                    reason = ("user_deferred" if metadata and metadata.availability == "skipped"
                              else "ambiguous_information" if metadata and metadata.availability == "conflicting"
                              else "user_unsure" if metadata and metadata.availability == "unknown"
                              else "verification_needed" if criterion.reason_code == "insufficient_precision"
                              else "missing_information")
                    entry["reasons"].add(reason)
    old_tasks = updated.resolution.tasks
    for path, obligation in obligations.items():
        task_id = str(uuid5(NAMESPACE_URL, f"ilera:screening:{updated.id}:{path}"))
        previous = old_tasks.get(task_id)
        template = by_path.get(path)
        root, field = path.split(".", 1)
        subject = {"care_recipient": "the care recipient's", "caregiver": "your", "household": "the household's"}[root]
        label = f"{subject} {field.replace('_', ' ')}"
        programs = sorted(obligation["programs"])
        task = ResolutionTask(
            id=task_id, case_id=updated.id, profile_path=path,
            primary_program_id=programs[0], related_program_ids=programs[1:],
            criterion_ids=sorted(obligation["criteria"]), reasons=sorted(obligation["reasons"]),
            title=template.title if template else f"Confirm {label}",
            description=template.description if template else f"Provide {label} to help complete the eligibility assessment.",
            guided_steps=template.guided_steps if template else [f"Enter the {label} when you have the information available."],
            resources=template.resources if template else [],
            acceptable_evidence_types=template.acceptable_evidence_types if template else [],
            methods=template.methods if template else [ResolutionMethod(kind="manual_entry", label="Enter information")],
            input_schema=TypeAdapter(fact_registry()[path]).json_schema(),
            template_id=template.template_id if template else None,
            category=template.category if template else "general",
            state="deferred" if previous and previous.state == "deferred" else "available",
            completed_at=previous.completed_at if previous else None,
            reopen_reason=("The fact is unresolved in the current assessment." if previous and previous.state == "resolved"
                           else previous.reopen_reason if previous else None),
        )
        old_tasks[task_id] = task
    wanted = set(obligations)
    for task in old_tasks.values():
        if task.profile_path not in wanted and task.state in {"available", "deferred"}:
            task.state = "resolved" if known_fact(updated, task.profile_path)[0] else "superseded"
    if updated.resolution.tasks != profile.resolution.tasks:
        updated.resolution.revision += 1
    return updated, evaluations


def complete_resolution(profile: CaseProfile, task_id: str, request: CompletionRequest,
                        policies: list[ProgramPolicy], templates: list[ResolutionTemplate] | None = None
                        ) -> tuple[CaseProfile, list[ProgramEvaluation]]:
    digest = hashlib.sha256(json.dumps({"task_id": task_id, "method": request.method, "value": request.value},
                                      sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    receipt = profile.resolution.receipts.get(request.idempotency_key)
    if receipt:
        if receipt.request_digest != digest or receipt.task_id != task_id:
            raise ResolutionConflict("Idempotency key already used for a different result")
        return refresh_resolution(profile, policies, templates)
    updated, evaluations = refresh_resolution(profile, policies, templates)
    if (request.expected_fact_revision != updated.fact_revision
            or request.expected_task_revision != updated.resolution.revision):
        raise ResolutionConflict("Assessment changed; reload tasks before submitting")
    task = updated.resolution.tasks.get(task_id)
    if not task:
        raise KeyError(task_id)
    if task.state not in {"available", "deferred"}:
        raise ResolutionConflict("Task no longer needs a result")
    if request.method not in {method.kind for method in task.methods}:
        raise ValueError("Completion method is unavailable for this task")
    write_fact(updated, task.profile_path, request.value, source_ref=f"resolution:{task_id}")
    # Final state is derived from the remaining requirements, not from a 'done' flag.
    updated, evaluations = refresh_resolution(updated, policies, templates)
    task = updated.resolution.tasks[task_id]
    if task.state == "resolved":
        task.completed_at = datetime.now(timezone.utc).isoformat()
        task.reopen_reason = None
    updated.resolution.receipts[request.idempotency_key] = CompletionReceipt(
        task_id=task_id, request_digest=digest, fact_revision=updated.fact_revision)
    return updated, evaluations


def defer_resolution(profile: CaseProfile, task_id: str, expected_revision: int) -> CaseProfile:
    if profile.resolution.revision != expected_revision:
        raise ResolutionConflict("Tasks changed; reload before saving")
    updated = profile.model_copy(deep=True)
    task = updated.resolution.tasks[task_id]
    if task.state not in {"available", "deferred"}:
        raise ResolutionConflict("Task is no longer active")
    if task.state != "deferred":
        task.state = "deferred"
        updated.resolution.revision += 1
    return updated
