from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from jb_orchestrator.domain import DomainValidationError, InvalidStateTransition, Run, RunStatus


def test_run_follows_happy_path_and_sets_lifecycle_timestamps() -> None:
    run = Run(request_id=uuid4())
    started_at = datetime(2026, 9, 1, 1, tzinfo=UTC)
    completed_at = started_at + timedelta(minutes=5)

    run.transition_to(RunStatus.PLANNING, at=started_at)
    run.transition_to(RunStatus.READY)
    run.transition_to(RunStatus.RUNNING)
    run.transition_to(RunStatus.VERIFYING)
    run.transition_to(RunStatus.SUCCEEDED, at=completed_at)

    assert run.status is RunStatus.SUCCEEDED
    assert run.started_at == started_at
    assert run.completed_at == completed_at
    assert run.is_terminal
    assert run.version == 6


def test_generic_workflow_can_start_directly_in_approval() -> None:
    run = Run(request_id=uuid4())
    started_at = datetime(2026, 9, 1, 1, tzinfo=UTC)

    run.transition_to(RunStatus.AWAITING_APPROVAL, at=started_at)
    run.transition_to(RunStatus.RUNNING)

    assert run.started_at == started_at


def test_verification_can_return_to_running_for_a_repair_loop() -> None:
    run = Run(request_id=uuid4())
    run.transition_to(RunStatus.PLANNING)
    run.transition_to(RunStatus.READY)
    run.transition_to(RunStatus.RUNNING)
    original_started_at = run.started_at
    run.transition_to(RunStatus.VERIFYING)

    run.transition_to(RunStatus.RUNNING)

    assert run.started_at == original_started_at


def test_invalid_transition_is_rejected_without_mutation() -> None:
    run = Run(request_id=uuid4())

    with pytest.raises(InvalidStateTransition, match="queued"):
        run.transition_to(RunStatus.VERIFYING)

    assert run.status is RunStatus.QUEUED
    assert run.version == 1


def test_failed_run_requires_a_reason() -> None:
    run = Run(request_id=uuid4())
    run.transition_to(RunStatus.PLANNING)

    with pytest.raises(DomainValidationError, match="reason"):
        run.fail("  ")

    run.fail("planner unavailable")

    assert run.status is RunStatus.FAILED
    assert run.failure_reason == "planner unavailable"
