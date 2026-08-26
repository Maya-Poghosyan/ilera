"""A specialist that goes silent must not cost the caregiver its program without a fight: the run
nudges it first, and if it still never reports, the plan says which program it is missing."""

import asyncio
import uuid

import pytest

from app import main, store
from app.integrations import band
from app.models import CaseProfile, SpecialistFinding

SPECIALISTS = ["ihss", "medical"]


@pytest.fixture
def fast_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real budgets are minutes long; the logic under test is the same at milliseconds."""
    monkeypatch.setattr(main, "_POLL_INTERVAL", 0.01)
    monkeypatch.setattr(main, "_STRAGGLER_GRACE", 0.05)
    monkeypatch.setattr(main, "_FINDINGS_TIMEOUT", 3)
    monkeypatch.setattr(main, "_STRATEGY_TIMEOUT", 3)
    monkeypatch.setattr(main, "_WATCHDOG_INTERVAL", 3)


def _case() -> str:
    profile = CaseProfile(id=f"case-{uuid.uuid4().hex}")
    store.save_profile(profile)
    return profile.id


def _report(case_id: str, doc_key: str) -> None:
    profile = store.get_profile(case_id)
    assert profile is not None
    profile.findings[doc_key] = SpecialistFinding(
        program=doc_key, match_level="likely", notes=["fine"], complete=True
    )
    store.save_profile(profile)


def _patch_band(monkeypatch: pytest.MonkeyPatch, seeded: list[list[str]]) -> None:
    async def start_case_room(profile: CaseProfile) -> tuple[str, list[str]]:
        return "room-1", list(SPECIALISTS)

    async def seed_specialists(profile: CaseProfile, chat_id: str, batch: list[str]) -> None:
        seeded.append(list(batch))

    async def trigger_synthesis(chat_id: str, findings_summary: str) -> None:
        profile = store.get_profile(store.get_case_for_room(chat_id) or "")
        if profile is not None:
            profile.strategy = "- Apply for IHSS through your county office."
            profile.strategy_complete = True
            store.save_profile(profile)

    async def noop(*args: object, **kwargs: object) -> int:
        return 0

    monkeypatch.setattr(band, "start_case_room", start_case_room)
    monkeypatch.setattr(band, "seed_specialists", seed_specialists)
    monkeypatch.setattr(band, "trigger_synthesis", trigger_synthesis)
    monkeypatch.setattr(band, "drain_routing_queue", noop)
    monkeypatch.setattr(band, "settle_room", noop)
    monkeypatch.setattr(band, "force_ack_stale_peer_messages", noop)


def test_a_silent_specialist_is_nudged_before_it_is_dropped(
    monkeypatch: pytest.MonkeyPatch, fast_run: None
) -> None:
    case_id = _case()
    seeded: list[list[str]] = []
    _patch_band(monkeypatch, seeded)
    store.map_room_to_case("room-1", case_id)

    async def run() -> None:
        task = asyncio.create_task(main._run_case_eligibility(case_id))
        await asyncio.sleep(0.02)
        _report(case_id, "ihss")
        # medical stays silent through the first grace period, so it gets re-mentioned; it answers
        # the nudge, which is the point of sending one.
        while len(seeded) < 2:
            await asyncio.sleep(0.01)
        _report(case_id, "medical")
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(run())

    assert seeded[0] == SPECIALISTS
    assert seeded[1] == ["medical"]
    profile = store.get_profile(case_id)
    assert profile is not None
    assert profile.unassessed_specialists == []
    assert profile.strategy_complete


def test_a_specialist_that_ignores_the_nudge_is_named_as_unassessed(
    monkeypatch: pytest.MonkeyPatch, fast_run: None
) -> None:
    case_id = _case()
    seeded: list[list[str]] = []
    _patch_band(monkeypatch, seeded)
    store.map_room_to_case("room-1", case_id)

    async def run() -> None:
        task = asyncio.create_task(main._run_case_eligibility(case_id))
        await asyncio.sleep(0.02)
        _report(case_id, "ihss")
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(run())

    assert seeded[1] == ["medical"]
    profile = store.get_profile(case_id)
    assert profile is not None
    # The strategy was synthesized from one finding, and says so.
    assert profile.strategy_complete
    assert profile.unassessed_specialists == ["medical"]
