"""Application services for notification subscriptions and delivery intents."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import DomainEvent
from jb_orchestrator.notifications import (
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationFailureCode,
    NotificationSubscription,
)


class NotificationService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def create_subscription(
        self,
        project_id: UUID,
        *,
        provider_key: str,
        destination_ref: str,
        event_types: tuple[NotificationEventType, ...],
        created_by: str,
    ) -> tuple[NotificationSubscription, bool]:
        subscription = NotificationSubscription(
            project_id=project_id,
            provider_key=provider_key,
            destination_ref=destination_ref,
            event_types=event_types,
            created_by=created_by,
        )
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.projects.get(project_id) is None:
                raise ResourceNotFound(f"project not found: {project_id}")
            if not await unit_of_work.notification_subscriptions.try_add(subscription):
                existing = await unit_of_work.notification_subscriptions.get_destination(
                    project_id,
                    subscription.provider_key,
                    subscription.destination_ref,
                )
                if existing is None:  # pragma: no cover - database invariant
                    raise RuntimeError("notification subscription uniqueness claim disappeared")
                if existing.event_types != subscription.event_types:
                    raise ResourceConflict(
                        "notification destination is already registered with different event types"
                    )
                return existing, True
            await unit_of_work.events.append(
                self._subscription_event(subscription, "notification.subscription_created")
            )
            await unit_of_work.commit()
            return subscription, False

    async def configure_subscription(
        self,
        project_id: UUID,
        subscription_id: UUID,
        *,
        event_types: tuple[NotificationEventType, ...],
        enabled: bool,
        configured_by: str,
    ) -> NotificationSubscription:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.projects.get(project_id) is None:
                raise ResourceNotFound(f"project not found: {project_id}")
            subscription = await unit_of_work.notification_subscriptions.get(
                subscription_id,
                for_update=True,
            )
            if subscription is None or subscription.project_id != project_id:
                raise ResourceNotFound(f"notification subscription not found: {subscription_id}")
            subscription.configure(event_types=event_types, enabled=enabled)
            await unit_of_work.notification_subscriptions.save(subscription)
            await unit_of_work.events.append(
                self._subscription_event(
                    subscription,
                    "notification.subscription_configured",
                    actor=configured_by,
                )
            )
            await unit_of_work.commit()
            return subscription

    async def list_subscriptions(
        self, project_id: UUID, *, limit: int = 100
    ) -> list[NotificationSubscription]:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.projects.get(project_id) is None:
                raise ResourceNotFound(f"project not found: {project_id}")
            return await unit_of_work.notification_subscriptions.list_by_project(
                project_id,
                limit=limit,
            )

    async def list_deliveries(
        self,
        project_id: UUID,
        *,
        status: NotificationDeliveryStatus | None = None,
        limit: int = 100,
    ) -> list[NotificationDelivery]:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.projects.get(project_id) is None:
                raise ResourceNotFound(f"project not found: {project_id}")
            return await unit_of_work.notification_deliveries.list_by_project(
                project_id,
                status=status,
                limit=limit,
            )

    async def claim_next(
        self, *, worker_id: str, provider_key: str, lease_seconds: int = 300
    ) -> NotificationDelivery | None:
        async with self._unit_of_work_factory() as unit_of_work:
            delivery = await unit_of_work.notification_deliveries.claim_next(
                worker_id=worker_id,
                provider_key=provider_key,
                lease_seconds=lease_seconds,
            )
            if delivery is None:
                return None
            await self._delivery_event(unit_of_work, delivery, "notification.delivery_claimed")
            await unit_of_work.commit()
            return delivery

    async def succeed(
        self, delivery_id: UUID, lease_token: UUID, result: dict[str, Any]
    ) -> NotificationDelivery:
        return await self._finish(delivery_id, lease_token, result=result)

    async def fail(
        self,
        delivery_id: UUID,
        lease_token: UUID,
        reason: str,
        *,
        code: NotificationFailureCode = NotificationFailureCode.UNEXPECTED,
    ) -> NotificationDelivery:
        return await self._finish(
            delivery_id,
            lease_token,
            failure_reason=reason,
            failure_code=code,
        )

    async def _finish(
        self,
        delivery_id: UUID,
        lease_token: UUID,
        *,
        result: dict[str, Any] | None = None,
        failure_reason: str | None = None,
        failure_code: NotificationFailureCode | None = None,
    ) -> NotificationDelivery:
        async with self._unit_of_work_factory() as unit_of_work:
            delivery = await unit_of_work.notification_deliveries.get(delivery_id, for_update=True)
            if delivery is None:
                raise ResourceNotFound(f"notification delivery not found: {delivery_id}")
            if failure_reason is None:
                delivery.succeed(lease_token, result or {})
                event_type = "notification.delivery_succeeded"
            else:
                delivery.fail(
                    lease_token,
                    failure_reason,
                    code=failure_code or NotificationFailureCode.UNEXPECTED,
                )
                event_type = "notification.delivery_failed"
            await unit_of_work.notification_deliveries.save(delivery)
            await self._delivery_event(unit_of_work, delivery, event_type)
            await unit_of_work.commit()
            return delivery

    @staticmethod
    def _subscription_event(
        subscription: NotificationSubscription,
        event_type: str,
        *,
        actor: str | None = None,
    ) -> DomainEvent:
        return DomainEvent(
            aggregate_type="project",
            aggregate_id=subscription.project_id,
            event_type=event_type,
            payload={
                "subscription_id": str(subscription.id),
                "provider_key": subscription.provider_key,
                "destination_ref": subscription.destination_ref,
                "event_types": [value.value for value in subscription.event_types],
                "enabled": subscription.enabled,
                "actor": (actor or subscription.created_by).strip() or "anonymous",
            },
        )

    @staticmethod
    async def _delivery_event(
        unit_of_work: UnitOfWork,
        delivery: NotificationDelivery,
        event_type: str,
    ) -> None:
        await unit_of_work.events.append(
            DomainEvent(
                aggregate_type="notification_delivery",
                aggregate_id=delivery.id,
                event_type=event_type,
                payload={
                    "project_id": str(delivery.project_id),
                    "provider_key": delivery.provider_key,
                    "event_type": delivery.event_type.value,
                    "status": delivery.status.value,
                    "worker_id": delivery.worker_id,
                    "attempt_count": delivery.attempt_count,
                    "failure_reason": delivery.failure_reason,
                    "failure_code": (
                        delivery.failure_code.value if delivery.failure_code else None
                    ),
                },
            )
        )


async def enqueue_notification_deliveries(
    unit_of_work: UnitOfWork,
    event: DomainEvent,
) -> int:
    """Create immutable delivery intents for one supported project event."""

    try:
        notification_event_type = NotificationEventType(event.event_type)
    except ValueError:
        return 0
    alert_value = event.payload.get("alert_id")
    if not isinstance(alert_value, str):
        raise RuntimeError("notification source event requires an alert_id")
    alert_id = UUID(alert_value)
    subscriptions = await unit_of_work.notification_subscriptions.list_by_project(
        event.aggregate_id,
        enabled=True,
        limit=500,
    )
    created = 0
    for subscription in subscriptions:
        if not subscription.accepts(notification_event_type):
            continue
        delivery = NotificationDelivery(
            subscription_id=subscription.id,
            project_id=event.aggregate_id,
            event_id=event.id,
            alert_id=alert_id,
            event_type=notification_event_type,
            provider_key=subscription.provider_key,
            destination_ref=subscription.destination_ref,
            payload={
                "event_id": str(event.id),
                "event_type": event.event_type,
                "project_id": str(event.aggregate_id),
                "occurred_at": event.occurred_at.isoformat(),
                "data": event.payload,
            },
            idempotency_key=f"notification:{subscription.id}:{event.id}",
        )
        if await unit_of_work.notification_deliveries.try_add(delivery):
            created += 1
    return created
