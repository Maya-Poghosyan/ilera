"""QA scenarios: a realistic household goes through the real intake API into Postgres, and the
stored case is run through the same deterministic gates the eligibility pipeline uses."""
import pytest

from app.store import get_profile
from durable.tools.eligibility_checks import GATES
from tests.intake_helpers import complete_current_intake


def submit(client, orchestrator, **answers):
    body = complete_current_intake(**answers)
    response = client.post("/api/intake", json={"answers": body})
    assert response.status_code == 200, response.text
    case_id = response.json()["id"]
    assert orchestrator == [case_id], "a valid intake starts eligibility exactly once"
    return get_profile(case_id)


def gate(profile, program):
    skip, _, level = GATES[program](profile)
    return ("decided:" + level) if skip else "needs_specialist"


def test_recipient_already_on_medicaid_is_shown_eligible_for_medi_cal(client, orchestrator):
    # The reported bug: someone already on Medi-Cal was shown as not eligible.
    profile = submit(client, orchestrator, **{
        "recipient.medicaid_covered": True, "recipient.coverage_and_benefits": ["Medicaid"]})
    assert gate(profile, "medical") == "decided:very_likely"


def test_recipient_with_no_coverage_gets_a_full_medi_cal_assessment(client, orchestrator):
    profile = submit(client, orchestrator, **{
        "recipient.medicaid_covered": False, "recipient.coverage_and_benefits": ["No health coverage"]})
    assert gate(profile, "medical") == "needs_specialist"
    assert gate(profile, "medicare") == "needs_specialist"


@pytest.mark.parametrize("status", ["Retired", "Not currently employed", "Self-employed", "Employed full time"])
def test_paid_family_leave_is_never_ruled_out_from_employment_status_alone(client, orchestrator, status):
    profile = submit(client, orchestrator, **{"caregiver.employment_status": status})
    assert gate(profile, "pfl") == "needs_specialist"


def test_unsure_answers_never_rule_a_program_out(client, orchestrator):
    # complete_current_intake answers every uncertain question with "I'm not sure".
    profile = submit(client, orchestrator)
    for program in GATES:
        assert gate(profile, program) != "decided:none", program
