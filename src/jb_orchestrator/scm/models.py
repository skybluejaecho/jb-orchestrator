"""Provider-neutral source-control publication models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from jb_orchestrator.domain.exceptions import DomainValidationError, InvalidStateTransition


class ScmPublicationStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True, kw_only=True)
class ScmPublication:
    """One idempotent, leaseable request to publish a managed branch for review."""

    external_execution_id: UUID
    provider_key: str
    repository: str
    source_branch: str
    target_branch: str
    title: str
    body: str
    workspace_scope: str
    idempotency_key: str
    requested_by: str
    id: UUID = field(default_factory=uuid4)
    status: ScmPublicationStatus = ScmPublicationStatus.PENDING
    worker_id: str | None = None
    lease_token: UUID | None = None
    lease_expires_at: datetime | None = None
    result: dict[str, Any] | None = None
    failure_reason: str | None = None
    attempt_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "provider_key",
            "repository",
            "source_branch",
            "target_branch",
            "title",
            "workspace_scope",
            "idempotency_key",
            "requested_by",
        ):
            normalized = getattr(self, field_name).strip()
            if not normalized:
                raise DomainValidationError(f"SCM publication {field_name} must not be empty")
            setattr(self, field_name, normalized)
        self.body = self.body.strip()
        if self.source_branch == self.target_branch:
            raise DomainValidationError(
                "SCM publication source_branch and target_branch must differ"
            )
        if self.attempt_count < 0:
            raise DomainValidationError("SCM publication attempt_count must not be negative")

    @property
    def is_terminal(self) -> bool:
        return self.status in {ScmPublicationStatus.SUCCEEDED, ScmPublicationStatus.FAILED}

    def claim(self, worker_id: str, *, lease_seconds: int, at: datetime | None = None) -> None:
        if self.is_terminal:
            raise InvalidStateTransition("terminal SCM publication cannot be claimed")
        if not worker_id.strip() or lease_seconds <= 0:
            raise DomainValidationError("SCM publication claim requires worker and positive lease")
        changed_at = at or datetime.now(UTC)
        self.status = ScmPublicationStatus.CLAIMED
        self.attempt_count += 1
        self.worker_id = worker_id.strip()
        self.lease_token = uuid4()
        self.lease_expires_at = changed_at + timedelta(seconds=lease_seconds)
        self.updated_at = changed_at

    def retry(self, *, at: datetime | None = None) -> None:
        if self.status is not ScmPublicationStatus.FAILED:
            raise InvalidStateTransition("only failed SCM publication can be retried")
        changed_at = at or datetime.now(UTC)
        self.status = ScmPublicationStatus.PENDING
        self.worker_id = None
        self.lease_token = None
        self.lease_expires_at = None
        self.result = None
        self.failure_reason = None
        self.completed_at = None
        self.updated_at = changed_at

    def succeed(
        self, lease_token: UUID, result: dict[str, Any], *, at: datetime | None = None
    ) -> None:
        self._require_claim(lease_token)
        changed_at = at or datetime.now(UTC)
        self.status = ScmPublicationStatus.SUCCEEDED
        self.result = result
        self.failure_reason = None
        self.lease_expires_at = None
        self.completed_at = changed_at
        self.updated_at = changed_at

    def fail(self, lease_token: UUID, reason: str, *, at: datetime | None = None) -> None:
        self._require_claim(lease_token)
        normalized = reason.strip()
        if not normalized:
            raise DomainValidationError("SCM publication failure reason must not be empty")
        changed_at = at or datetime.now(UTC)
        self.status = ScmPublicationStatus.FAILED
        self.failure_reason = normalized
        self.lease_expires_at = None
        self.completed_at = changed_at
        self.updated_at = changed_at

    def _require_claim(self, lease_token: UUID) -> None:
        if self.status is not ScmPublicationStatus.CLAIMED or self.lease_token != lease_token:
            raise InvalidStateTransition("SCM publication lease is not owned by this worker")


@dataclass(frozen=True, slots=True, kw_only=True)
class ScmPublicationRequest:
    """A credential-free request to publish one branch for human review."""

    repository: str
    workspace_path: str
    source_branch: str
    target_branch: str
    title: str
    body: str
    idempotency_key: str

    def __post_init__(self) -> None:
        for field_name in (
            "repository",
            "workspace_path",
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
