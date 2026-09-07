"""Durable notification subscriptions and delivery intents."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from jb_orchestrator.domain import DomainValidationError

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


@dataclass(frozen=True, slots=True, kw_only=True)
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
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not PROVIDER_KEY_PATTERN.fullmatch(self.provider_key):
            raise DomainValidationError("notification provider key is invalid")
        if not self.destination_ref or len(self.destination_ref) > 255:
            raise DomainValidationError("notification delivery destination reference is invalid")
        if not self.idempotency_key or len(self.idempotency_key) > 255:
            raise DomainValidationError("notification delivery idempotency key is invalid")
