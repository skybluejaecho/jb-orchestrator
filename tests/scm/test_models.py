import pytest

from jb_orchestrator.domain import DomainValidationError
from jb_orchestrator.scm import ScmPublicationRequest, ScmPublicationResult


def test_publication_request_normalizes_credential_free_review_input() -> None:
    request = ScmPublicationRequest(
        repository="  skybluejaecho/jb-orchestrator ",
        source_branch=" feature/ORCH-049 ",
        target_branch=" develop ",
        title=" ORCH-049 ",
        body=" body\n",
        idempotency_key=" request-1 ",
    )

    assert request.repository == "skybluejaecho/jb-orchestrator"
    assert request.source_branch == "feature/ORCH-049"
    assert request.target_branch == "develop"
    assert request.body == "body"
    assert not hasattr(request, "token")


@pytest.mark.parametrize(
    "field_name",
    ["repository", "source_branch", "target_branch", "title", "idempotency_key"],
)
def test_publication_request_rejects_empty_required_fields(field_name: str) -> None:
    values = {
        "repository": "owner/repository",
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
