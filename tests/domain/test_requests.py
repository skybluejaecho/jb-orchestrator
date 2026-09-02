from uuid import uuid4

import pytest

from jb_orchestrator.domain import (
    DomainValidationError,
    InvalidStateTransition,
    RequestStatus,
    UserRequest,
)


def test_request_preserves_normalized_user_intent() -> None:
    request = UserRequest(project_id=uuid4(), title="  First run  ", prompt="  Build it  ")

    assert request.title == "First run"
    assert request.prompt == "Build it"
    assert request.status is RequestStatus.RECEIVED


def test_terminal_request_cannot_change_status() -> None:
    request = UserRequest(project_id=uuid4(), prompt="Build it")
    request.activate()
    request.complete()

    with pytest.raises(InvalidStateTransition, match="completed"):
        request.activate()


def test_request_cannot_complete_before_activation() -> None:
    request = UserRequest(project_id=uuid4(), prompt="Build it")

    with pytest.raises(InvalidStateTransition, match="received"):
        request.complete()


def test_request_rejects_empty_prompt() -> None:
    with pytest.raises(DomainValidationError, match="prompt"):
        UserRequest(project_id=uuid4(), prompt="  ")
