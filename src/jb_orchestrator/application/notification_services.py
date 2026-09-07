"""Application services for notification subscriptions and delivery intents."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import DomainEvent
from jb_orchestrator.notifications import (
    NotificationAttemptStatus,
    NotificationAttemptTrigger,
    NotificationDelivery,
    NotificationDeliveryAttempt,
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

    async def list_attempts(
        self, project_id: UUID, delivery_id: UUID, *, limit: int = 100
    ) -> list[NotificationDeliveryAttempt]:
        async with self._unit_of_work_factory() as unit_of_work:
            await self._project_delivery(unit_of_work, project_id, delivery_id)
            return await unit_of_work.notification_delivery_attempts.list_for_delivery(
                delivery_id, limit=limit
            )

    async def retry(
        self, project_id: UUID, delivery_id: UUID, *, requested_by: str
    ) -> tuple[NotificationDelivery, bool]:
        async with self._unit_of_work_factory() as unit_of_work:
            delivery = await self._project_delivery(
                unit_of_work, project_id, delivery_id, for_update=True
            )
            if delivery.status in {
                NotificationDeliveryStatus.PENDING,
                NotificationDeliveryStatus.CLAIMED,
            }:
                return delivery, True
            if delivery.status is NotificationDeliveryStatus.SUCCEEDED:
                raise ResourceConflict("succeeded notification delivery cannot be retried")
            delivery.retry()
            await unit_of_work.notification_deliveries.save(delivery)
            await self._delivery_event(
                unit_of_work,
                delivery,
                "notification.delivery_retried",
                actor=requested_by.strip() or "anonymous",
            )
            await unit_of_work.commit()
            return delivery, False

    async def claim_next(
        self, *, worker_id: str, provider_key: str, lease_seconds: int = 300
    ) -> NotificationDelivery | None:
        async with self._unit_of_work_factory() as unit_of_work:
            claim = await unit_of_work.notification_deliveries.claim_next(
                worker_id=worker_id,
                provider_key=provider_key,
                lease_seconds=lease_seconds,
            )
            if claim is None:
                return None
            delivery = claim.delivery
            if delivery.lease_token is None:  # pragma: no cover - domain invariant
                raise RuntimeError("claimed notification delivery has no lease token")
            if claim.trigger is NotificationAttemptTrigger.LEASE_RECOVERY:
                previous = await unit_of_work.notification_delivery_attempts.get(
                    delivery.id,
                    delivery.attempt_count - 1,
                    for_update=True,
                )
                if previous is not None and previous.status is NotificationAttemptStatus.CLAIMED:
                    previous.fail(
                        previous.lease_token,
                        "notification delivery lease expired before completion",
                        code=NotificationFailureCode.LEASE_EXPIRED,
                        at=delivery.updated_at,
                    )
                    await unit_of_work.notification_delivery_attempts.save(previous)
            await unit_of_work.notification_delivery_attempts.add(
                NotificationDeliveryAttempt(
                    delivery_id=delivery.id,
                    attempt_number=delivery.attempt_count,
                    trigger=claim.trigger,
                    worker_id=delivery.worker_id or worker_id,
                    lease_token=delivery.lease_token,
                    started_at=delivery.updated_at,
                )
            )
            await self._delivery_event(
                unit_of_work,
                delivery,
                "notification.delivery_claimed",
                attempt_trigger=claim.trigger,
            )
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
            attempt = await unit_of_work.notification_delivery_attempts.get(
                delivery.id, delivery.attempt_count, for_update=True
            )
            if attempt is None:
                if delivery.worker_id is None:
                    raise ResourceConflict("claimed notification delivery has no worker")
                attempt = NotificationDeliveryAttempt(
                    delivery_id=delivery.id,
                    attempt_number=delivery.attempt_count,
                    trigger=NotificationAttemptTrigger.LEASE_RECOVERY,
                    worker_id=delivery.worker_id,
                    lease_token=lease_token,
                    started_at=delivery.updated_at,
                )
                await unit_of_work.notification_delivery_attempts.add(attempt)
            finished_at = datetime.now(UTC)
            if failure_reason is None:
                delivery.succeed(lease_token, result or {}, at=finished_at)
                attempt.succeed(lease_token, result or {}, at=finished_at)
                event_type = "notification.delivery_succeeded"
            else:
                delivery.fail(
                    lease_token,
                    failure_reason,
                    code=failure_code or NotificationFailureCode.UNEXPECTED,
                    at=finished_at,
                )
                attempt.fail(
                    lease_token,
                    failure_reason,
                    code=failure_code or NotificationFailureCode.UNEXPECTED,
                    at=finished_at,
                )
                event_type = "notification.delivery_failed"
            await unit_of_work.notification_deliveries.save(delivery)
            await unit_of_work.notification_delivery_attempts.save(attempt)
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
        *,
        actor: str | None = None,
        attempt_trigger: NotificationAttemptTrigger | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "project_id": str(delivery.project_id),
            "provider_key": delivery.provider_key,
            "event_type": delivery.event_type.value,
            "status": delivery.status.value,
            "worker_id": delivery.worker_id,
            "attempt_count": delivery.attempt_count,
            "failure_reason": delivery.failure_reason,
            "failure_code": delivery.failure_code.value if delivery.failure_code else None,
        }
        if actor is not None:
            payload["actor"] = actor
        if attempt_trigger is not None:
            payload["attempt_trigger"] = attempt_trigger.value
        await unit_of_work.events.append(
            DomainEvent(
                aggregate_type="notification_delivery",
                aggregate_id=delivery.id,
                event_type=event_type,
                payload=payload,
            )
        )

    @staticmethod
    async def _project_delivery(
        unit_of_work: UnitOfWork,
        project_id: UUID,
        delivery_id: UUID,
        *,
        for_update: bool = False,
    ) -> NotificationDelivery:
        if await unit_of_work.projects.get(project_id) is None:
            raise ResourceNotFound(f"project not found: {project_id}")
        delivery = await unit_of_work.notification_deliveries.get(
            delivery_id, for_update=for_update
        )
        if delivery is None or delivery.project_id != project_id:
            raise ResourceNotFound(f"notification delivery not found: {delivery_id}")
        return delivery


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
