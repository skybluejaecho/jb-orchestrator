from uuid import uuid4

import pytest

from jb_orchestrator.domain import DomainValidationError
from jb_orchestrator.scm import (
    ScmPublication,
    ScmPublicationFailureCode,
    ScmPublicationRequest,
    ScmPublicationResult,
)


def test_publication_request_normalizes_credential_free_review_input() -> None:
    request = ScmPublicationRequest(
        repository="  skybluejaecho/jb-orchestrator ",
        workspace_path=" C:/worktrees/orch-049 ",
        source_branch=" feature/ORCH-049 ",
        target_branch=" develop ",
        title=" ORCH-049 ",
        body=" body\n",
        idempotency_key=" request-1 ",
    )

    assert request.repository == "skybluejaecho/jb-orchestrator"
    assert request.workspace_path == "C:/worktrees/orch-049"
    assert request.source_branch == "feature/ORCH-049"
    assert request.target_branch == "develop"
    assert request.body == "body"
    assert not hasattr(request, "token")


@pytest.mark.parametrize(
    "field_name",
    [
        "repository",
        "workspace_path",
        "source_branch",
        "target_branch",
        "title",
        "idempotency_key",
    ],
)
def test_publication_request_rejects_empty_required_fields(field_name: str) -> None:
    values = {
        "repository": "owner/repository",
        "workspace_path": "C:/worktrees/review",
        "source_branch": "feature/work",
        "target_branch": "develop",
        "title": "Review work",
        "body": "",
        "idempotency_key": "request-1",
    }
    values[field_name] = "  "

    with pytest.raises(DomainValidationError, match=field_name):
        ScmPublicationRequest(**values)


def test_publication_request_requires_distinct_branches() -> None:
    with pytest.raises(DomainValidationError, match="must differ"):
        ScmPublicationRequest(
            repository="owner/repository",
            workspace_path="C:/worktrees/review",
            source_branch="develop",
            target_branch=" develop ",
            title="Review work",
            body="",
            idempotency_key="request-1",
        )


def test_publication_result_requires_provider_identifiers() -> None:
    with pytest.raises(DomainValidationError, match="review_url"):
        ScmPublicationResult(
            provider="github",
            repository="owner/repository",
            source_branch="feature/work",
            target_branch="develop",
            review_url=" ",
            review_id="49",
        )


def test_failed_publication_preserves_attempt_count_and_can_be_retried() -> None:
    publication = ScmPublication(
        external_execution_id=uuid4(),
        provider_key="github",
        repository="https://github.com/example/project.git",
        source_branch="feature/review",
        target_branch="develop",
        title="Review",
        body="",
        workspace_scope="scope-a",
        idempotency_key="publish-1",
        requested_by="jarvis",
    )
    publication.claim("worker-a", lease_seconds=30)
    assert publication.lease_token is not None
    publication.fail(
        publication.lease_token,
        "temporary failure",
        code=ScmPublicationFailureCode.PROVIDER_UNAVAILABLE,
        retryable=True,
    )

    assert publication.failure_code is ScmPublicationFailureCode.PROVIDER_UNAVAILABLE
    assert publication.failure_retryable is True

    publication.retry()

    assert publication.status.value == "pending"
    assert publication.attempt_count == 1
    assert publication.worker_id is None
    assert publication.lease_token is None
    assert publication.failure_reason is None
    assert publication.failure_code is None
    assert publication.failure_retryable is None
    assert publication.completed_at is None
