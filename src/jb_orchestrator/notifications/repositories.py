"""Persistence ports for notification subscriptions and deliveries."""

from typing import Protocol
from uuid import UUID

from jb_orchestrator.notifications.models import (
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationDeliveryClaim,
    NotificationDeliveryStatus,
    NotificationSubscription,
)


class NotificationSubscriptionRepository(Protocol):
    async def try_add(self, subscription: NotificationSubscription) -> bool: ...

    async def get(
        self, subscription_id: UUID, *, for_update: bool = False
    ) -> NotificationSubscription | None: ...

    async def get_destination(
        self, project_id: UUID, provider_key: str, destination_ref: str
    ) -> NotificationSubscription | None: ...

    async def list_by_project(
        self, project_id: UUID, *, enabled: bool | None = None, limit: int = 100
    ) -> list[NotificationSubscription]: ...

    async def save(self, subscription: NotificationSubscription) -> None: ...


class NotificationDeliveryRepository(Protocol):
    async def try_add(self, delivery: NotificationDelivery) -> bool: ...

    async def get(
        self, delivery_id: UUID, *, for_update: bool = False
    ) -> NotificationDelivery | None: ...

    async def claim_next(
        self, *, worker_id: str, provider_key: str, lease_seconds: int
    ) -> NotificationDeliveryClaim | None: ...

    async def list_by_project(
        self,
        project_id: UUID,
        *,
        status: NotificationDeliveryStatus | None = None,
        limit: int = 100,
    ) -> list[NotificationDelivery]: ...

    async def save(self, delivery: NotificationDelivery) -> None: ...


class NotificationDeliveryAttemptRepository(Protocol):
    async def add(self, attempt: NotificationDeliveryAttempt) -> None: ...

    async def get(
        self, delivery_id: UUID, attempt_number: int, *, for_update: bool = False
    ) -> NotificationDeliveryAttempt | None: ...

    async def list_for_delivery(
        self, delivery_id: UUID, *, limit: int = 100
    ) -> list[NotificationDeliveryAttempt]: ...

    async def save(self, attempt: NotificationDeliveryAttempt) -> None: ...
