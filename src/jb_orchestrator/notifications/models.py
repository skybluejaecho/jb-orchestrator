"""Durable notification subscriptions and delivery intents."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from jb_orchestrator.domain import DomainValidationError, InvalidStateTransition

PROVIDER_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")


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
    UNEXPECTED = "unexpected"


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
    attempt_count: int = 0
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

    def claim(self, worker_id: str, *, lease_seconds: int, at: datetime | None = None) -> None:
        changed_at = at or datetime.now(UTC)
        expired = (
            self.status is NotificationDeliveryStatus.CLAIMED
            and self.lease_expires_at is not None
            and self._as_utc(self.lease_expires_at) <= self._as_utc(changed_at)
        )
        if self.status is not NotificationDeliveryStatus.PENDING and not expired:
            raise InvalidStateTransition("notification delivery cannot be claimed")
        if not worker_id.strip() or lease_seconds <= 0:
            raise DomainValidationError("notification delivery claim requires worker and lease")
        self.status = NotificationDeliveryStatus.CLAIMED
        self.worker_id = worker_id.strip()
        self.lease_token = uuid4()
        self.lease_expires_at = changed_at + timedelta(seconds=lease_seconds)
        self.attempt_count += 1
        self.updated_at = changed_at

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
        at: datetime | None = None,
    ) -> None:
        self._require_claim(lease_token)
        normalized = reason.strip()
        if not normalized:
            raise DomainValidationError("notification delivery failure reason must not be empty")
        changed_at = at or datetime.now(UTC)
        self.status = NotificationDeliveryStatus.FAILED
        self.result = None
        self.failure_reason = normalized
        self.failure_code = code
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
