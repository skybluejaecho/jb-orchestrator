"""Durable notification subscriptions and delivery intents."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from jb_orchestrator.domain import DomainValidationError, InvalidStateTransition

PROVIDER_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
MAX_AUTOMATIC_RETRY_LIMIT = 10


class NotificationEventType(StrEnum):
    WORKER_READINESS_ALERTED = "worker.readiness_alerted"
    WORKER_READINESS_CRITICAL = "worker.readiness_critical"
    WORKER_READINESS_RESOLVED = "worker.readiness_resolved"


class NotificationDeliveryStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class NotificationFailureCode(StrEnum):
    PROVIDER_REJECTED = "provider_rejected"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    LEASE_EXPIRED = "lease_expired"
    UNEXPECTED = "unexpected"


class NotificationAttemptStatus(StrEnum):
    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class NotificationAttemptTrigger(StrEnum):
    INITIAL = "initial"
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    LEASE_RECOVERY = "lease_recovery"


class NotificationProviderFailure(RuntimeError):
    """Typed provider failure safe to persist across the adapter boundary."""

    def __init__(self, reason: str, *, code: NotificationFailureCode) -> None:
        super().__init__(reason)
        self.code = code


@dataclass(slots=True, kw_only=True)
class NotificationSubscription:
    project_id: UUID
    provider_key: str
    destination_ref: str
    event_types: tuple[NotificationEventType, ...]
    created_by: str
    enabled: bool = True
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.provider_key = self.provider_key.strip().lower()
        self.destination_ref = self.destination_ref.strip()
        self.created_by = self.created_by.strip() or "anonymous"
        self.event_types = tuple(sorted(set(self.event_types), key=lambda value: value.value))
        if not PROVIDER_KEY_PATTERN.fullmatch(self.provider_key):
            raise DomainValidationError("notification provider key is invalid")
        if not self.destination_ref or len(self.destination_ref) > 255:
            raise DomainValidationError(
                "notification destination reference must contain 1-255 characters"
            )
        if not self.event_types:
            raise DomainValidationError("notification subscription requires event types")
        if len(self.created_by) > 255:
            raise DomainValidationError("notification creator must contain at most 255 characters")

    def configure(
        self,
        *,
        event_types: tuple[NotificationEventType, ...],
        enabled: bool,
        at: datetime | None = None,
    ) -> None:
        normalized = tuple(sorted(set(event_types), key=lambda value: value.value))
        if not normalized:
            raise DomainValidationError("notification subscription requires event types")
        self.event_types = normalized
        self.enabled = enabled
        self.updated_at = at or datetime.now(UTC)

    def accepts(self, event_type: NotificationEventType) -> bool:
        return self.enabled and event_type in self.event_types


@dataclass(slots=True, kw_only=True)
class NotificationDelivery:
    subscription_id: UUID
    project_id: UUID
    event_id: UUID
    alert_id: UUID
    event_type: NotificationEventType
    provider_key: str
    destination_ref: str
    payload: dict[str, Any]
    idempotency_key: str
    status: NotificationDeliveryStatus = NotificationDeliveryStatus.PENDING
    worker_id: str | None = None
    lease_token: UUID | None = None
    lease_expires_at: datetime | None = None
    result: dict[str, Any] | None = None
    failure_reason: str | None = None
    failure_code: NotificationFailureCode | None = None
    failure_retryable: bool | None = None
    attempt_count: int = 0
    automatic_retry_limit: int = 0
    next_attempt_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not PROVIDER_KEY_PATTERN.fullmatch(self.provider_key):
            raise DomainValidationError("notification provider key is invalid")
        if not self.destination_ref or len(self.destination_ref) > 255:
            raise DomainValidationError("notification delivery destination reference is invalid")
        if not self.idempotency_key or len(self.idempotency_key) > 255:
            raise DomainValidationError("notification delivery idempotency key is invalid")
        if self.attempt_count < 0:
            raise DomainValidationError("notification delivery attempt_count must not be negative")
        if not 0 <= self.automatic_retry_limit <= MAX_AUTOMATIC_RETRY_LIMIT:
            raise DomainValidationError(
                "notification automatic_retry_limit must be between 0 and "
                f"{MAX_AUTOMATIC_RETRY_LIMIT}"
            )

    def claim(
        self, worker_id: str, *, lease_seconds: int, at: datetime | None = None
    ) -> NotificationAttemptTrigger:
        changed_at = at or datetime.now(UTC)
        trigger = self.claim_trigger(at=changed_at)
        expired = (
            self.status is NotificationDeliveryStatus.CLAIMED
            and self.lease_expires_at is not None
            and self._as_utc(self.lease_expires_at) <= self._as_utc(changed_at)
        )
        scheduled_retry = (
            self.status is NotificationDeliveryStatus.FAILED
            and self.failure_retryable is True
            and self.next_attempt_at is not None
            and self._as_utc(self.next_attempt_at) <= self._as_utc(changed_at)
            and self.attempt_count <= self.automatic_retry_limit
        )
        if (
            self.status is not NotificationDeliveryStatus.PENDING
            and not expired
            and not scheduled_retry
        ):
            raise InvalidStateTransition("notification delivery cannot be claimed")
        if not worker_id.strip() or lease_seconds <= 0:
            raise DomainValidationError("notification delivery claim requires worker and lease")
        self.status = NotificationDeliveryStatus.CLAIMED
        self.worker_id = worker_id.strip()
        self.lease_token = uuid4()
        self.lease_expires_at = changed_at + timedelta(seconds=lease_seconds)
        self.attempt_count += 1
        if scheduled_retry:
            self.failure_reason = None
            self.failure_code = None
            self.failure_retryable = None
            self.next_attempt_at = None
            self.completed_at = None
        self.updated_at = changed_at
        return trigger

    def claim_trigger(self, *, at: datetime | None = None) -> NotificationAttemptTrigger:
        changed_at = at or datetime.now(UTC)
        if (
            self.status is NotificationDeliveryStatus.CLAIMED
            and self.lease_expires_at is not None
            and self._as_utc(self.lease_expires_at) <= self._as_utc(changed_at)
        ):
            return NotificationAttemptTrigger.LEASE_RECOVERY
        if self.status is NotificationDeliveryStatus.FAILED:
            return NotificationAttemptTrigger.AUTOMATIC
        if self.attempt_count > 0:
            return NotificationAttemptTrigger.MANUAL
        return NotificationAttemptTrigger.INITIAL

    def retry(self, *, at: datetime | None = None) -> None:
        if self.status is not NotificationDeliveryStatus.FAILED:
            raise InvalidStateTransition("only failed notification delivery can be retried")
        changed_at = at or datetime.now(UTC)
        self.status = NotificationDeliveryStatus.PENDING
        self.worker_id = None
        self.lease_token = None
        self.lease_expires_at = None
        self.result = None
        self.failure_reason = None
        self.failure_code = None
        self.failure_retryable = None
        self.automatic_retry_limit = 0
        self.next_attempt_at = None
        self.completed_at = None
        self.updated_at = changed_at

    def cancel_automatic_retry(self, *, at: datetime | None = None) -> bool:
        if self.status is not NotificationDeliveryStatus.FAILED:
            raise InvalidStateTransition(
                "automatic retry can only be cancelled for failed notification delivery"
            )
        if self.next_attempt_at is None:
            return False
        changed_at = at or datetime.now(UTC)
        self.automatic_retry_limit = 0
        self.next_attempt_at = None
        self.updated_at = changed_at
        return True

    def succeed(
        self, lease_token: UUID, result: dict[str, Any], *, at: datetime | None = None
    ) -> None:
        self._require_claim(lease_token)
        changed_at = at or datetime.now(UTC)
        self.status = NotificationDeliveryStatus.SUCCEEDED
        self.result = result
        self.failure_reason = None
        self.failure_code = None
        self.lease_expires_at = None
        self.updated_at = changed_at
        self.completed_at = changed_at

    def fail(
        self,
        lease_token: UUID,
        reason: str,
        *,
        code: NotificationFailureCode,
        retryable: bool = False,
        automatic_retry_limit: int = 0,
        next_attempt_at: datetime | None = None,
        at: datetime | None = None,
    ) -> None:
        self._require_claim(lease_token)
        normalized = reason.strip()
        if not normalized:
            raise DomainValidationError("notification delivery failure reason must not be empty")
        if not 0 <= automatic_retry_limit <= MAX_AUTOMATIC_RETRY_LIMIT:
            raise DomainValidationError(
                f"automatic retry limit must be between 0 and {MAX_AUTOMATIC_RETRY_LIMIT}"
            )
        if next_attempt_at is not None and (
            not retryable or self.attempt_count > automatic_retry_limit
        ):
            raise DomainValidationError(
                "scheduled notification retry requires an available retry attempt"
            )
        changed_at = at or datetime.now(UTC)
        self.status = NotificationDeliveryStatus.FAILED
        self.result = None
        self.failure_reason = normalized
        self.failure_code = code
        self.failure_retryable = retryable
        self.automatic_retry_limit = automatic_retry_limit
        self.next_attempt_at = next_attempt_at
        self.lease_expires_at = None
        self.updated_at = changed_at
        self.completed_at = changed_at

    def _require_claim(self, lease_token: UUID) -> None:
        if self.status is not NotificationDeliveryStatus.CLAIMED or self.lease_token != lease_token:
            raise InvalidStateTransition("notification delivery lease is not owned")

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationDeliveryClaim:
    delivery: NotificationDelivery
    trigger: NotificationAttemptTrigger


@dataclass(slots=True, kw_only=True)
class NotificationDeliveryAttempt:
    delivery_id: UUID
    attempt_number: int
    trigger: NotificationAttemptTrigger
    worker_id: str
    lease_token: UUID
    id: UUID = field(default_factory=uuid4)
    status: NotificationAttemptStatus = NotificationAttemptStatus.CLAIMED
    result: dict[str, Any] | None = None
    failure_reason: str | None = None
    failure_code: NotificationFailureCode | None = None
    failure_retryable: bool | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        self.worker_id = self.worker_id.strip()
        if self.attempt_number <= 0 or not self.worker_id:
            raise DomainValidationError("notification attempt requires number and worker")

    def succeed(
        self, lease_token: UUID, result: dict[str, Any], *, at: datetime | None = None
    ) -> None:
        self._require_claim(lease_token)
        self.status = NotificationAttemptStatus.SUCCEEDED
        self.result = result
        self.finished_at = at or datetime.now(UTC)

    def fail(
        self,
        lease_token: UUID,
        reason: str,
        *,
        code: NotificationFailureCode,
        retryable: bool = False,
        at: datetime | None = None,
    ) -> None:
        self._require_claim(lease_token)
        normalized = reason.strip()
        if not normalized:
            raise DomainValidationError("notification attempt failure reason must not be empty")
        self.status = NotificationAttemptStatus.FAILED
        self.failure_reason = normalized
        self.failure_code = code
        self.failure_retryable = retryable
        self.finished_at = at or datetime.now(UTC)

    def _require_claim(self, lease_token: UUID) -> None:
        if self.status is not NotificationAttemptStatus.CLAIMED or self.lease_token != lease_token:
            raise InvalidStateTransition("notification attempt lease is not owned")


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationRequest:
    delivery_id: UUID
    project_id: UUID
    event_type: NotificationEventType
    destination_ref: str
    payload: dict[str, Any]
    idempotency_key: str


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationResult:
    """Provider-neutral evidence recorded after successful delivery."""

    output: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class NotificationProvider(Protocol):
    """Installed adapter that owns credentials and external delivery details."""

    async def deliver(self, request: NotificationRequest) -> NotificationResult: ...
