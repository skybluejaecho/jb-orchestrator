"""Provider-neutral source-control publication models."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from jb_orchestrator.domain.exceptions import DomainValidationError


@dataclass(frozen=True, slots=True, kw_only=True)
class ScmPublicationRequest:
    """A credential-free request to publish one branch for human review."""

    repository: str
    source_branch: str
    target_branch: str
    title: str
    body: str
    idempotency_key: str

    def __post_init__(self) -> None:
        for field_name in (
            "repository",
            "source_branch",
            "target_branch",
            "title",
            "idempotency_key",
        ):
            value = getattr(self, field_name)
            normalized = value.strip()
            if not normalized:
                raise DomainValidationError(f"SCM publication {field_name} must not be empty")
            object.__setattr__(self, field_name, normalized)
        object.__setattr__(self, "body", self.body.strip())
        if self.source_branch == self.target_branch:
            raise DomainValidationError(
                "SCM publication source_branch and target_branch must differ"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class ScmPublicationResult:
    """Stable identifiers returned after a branch is published for review."""

    provider: str
    repository: str
    source_branch: str
    target_branch: str
    review_url: str
    review_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "provider",
            "repository",
            "source_branch",
            "target_branch",
            "review_url",
            "review_id",
        ):
            value = getattr(self, field_name)
            normalized = value.strip()
            if not normalized:
                raise DomainValidationError(
                    f"SCM publication result {field_name} must not be empty"
                )
            object.__setattr__(self, field_name, normalized)


@runtime_checkable
class ScmPublisher(Protocol):
    """Adapter-owned authenticated boundary for push and review creation.

    Implementations obtain credentials from their own runtime environment. Credentials must never
    be embedded in :class:`ScmPublicationRequest` or persisted as orchestration data.
    """

    async def publish_review(self, request: ScmPublicationRequest) -> ScmPublicationResult: ...
