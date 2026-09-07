from datetime import UTC, datetime, timedelta

import pytest

from jb_orchestrator.application import NotificationService, WorkerPresenceService
from jb_orchestrator.application.exceptions import ResourceConflict
from jb_orchestrator.application.worker_readiness_services import WorkerReadinessService
from jb_orchestrator.domain import Project
from jb_orchestrator.notifications import (
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationFailureCode,
)
from jb_orchestrator.worker_presence import WorkerKind
from tests.support import MemoryStore, MemoryUnitOfWork
from tests.worker_presence.test_readiness import ready_execution


async def test_readiness_events_create_filtered_idempotent_delivery_intents() -> None:
    store = MemoryStore()
    project = Project(
        key="notification-project",
        name="Notification Project",
        repository_url="https://github.com/example/notification.git",
    )
    store.projects[project.id] = project
    execution = ready_execution(store, project, "openclaw")
    now = datetime(2026, 9, 7, tzinfo=UTC)
    execution.nodes["work"].updated_at = now - timedelta(minutes=10)
    notifications = NotificationService(lambda: MemoryUnitOfWork(store))
    subscription, replayed = await notifications.create_subscription(
        project.id,
        provider_key="webhook",
        destination_ref="operations-primary",
        event_types=(
            NotificationEventType.WORKER_READINESS_ALERTED,
            NotificationEventType.WORKER_READINESS_RESOLVED,
        ),
        created_by="operator",
    )
    readiness = WorkerReadinessService(lambda: MemoryUnitOfWork(store))

    first = await readiness.evaluate_project(project.id, at=now)
    await readiness.evaluate_project(project.id, at=now + timedelta(seconds=10))

    assert not replayed
    [alerted_delivery] = await notifications.list_deliveries(project.id)
    assert alerted_delivery.subscription_id == subscription.id
    assert alerted_delivery.alert_id == first.alerts[0].id
    assert alerted_delivery.event_type is NotificationEventType.WORKER_READINESS_ALERTED
    assert alerted_delivery.status is NotificationDeliveryStatus.PENDING
    assert alerted_delivery.destination_ref == "operations-primary"

    await WorkerPresenceService(lambda: MemoryUnitOfWork(store)).register(
        worker_id="worker-openclaw",
        kind=WorkerKind.EXECUTION,
        hostname="host-a",
        process_id=42,
        capabilities=("openclaw",),
    )
    await readiness.evaluate_project(project.id, at=now + timedelta(seconds=20))

    deliveries = await notifications.list_deliveries(project.id)
    assert {delivery.event_type for delivery in deliveries} == {
        NotificationEventType.WORKER_READINESS_ALERTED,
        NotificationEventType.WORKER_READINESS_RESOLVED,
    }
    assert len({delivery.idempotency_key for delivery in deliveries}) == 2


async def test_disabled_subscription_does_not_create_delivery() -> None:
    store = MemoryStore()
    project = Project(
        key="disabled-notifications",
        name="Disabled Notifications",
        repository_url="https://github.com/example/disabled.git",
    )
    store.projects[project.id] = project
    ready_execution(store, project, "specialized")
    service = NotificationService(lambda: MemoryUnitOfWork(store))
    subscription, _ = await service.create_subscription(
        project.id,
        provider_key="webhook",
        destination_ref="disabled-target",
        event_types=(NotificationEventType.WORKER_READINESS_ALERTED,),
        created_by="operator",
    )
    await service.configure_subscription(
        project.id,
        subscription.id,
        event_types=subscription.event_types,
        enabled=False,
        configured_by="operator",
    )

    await WorkerReadinessService(lambda: MemoryUnitOfWork(store)).evaluate_project(project.id)

    assert await service.list_deliveries(project.id) == []


async def test_duplicate_subscription_is_replayed_but_conflicting_filter_is_rejected() -> None:
    store = MemoryStore()
    project = Project(
        key="duplicate-notifications",
        name="Duplicate Notifications",
        repository_url="https://github.com/example/duplicate.git",
    )
    store.projects[project.id] = project
    service = NotificationService(lambda: MemoryUnitOfWork(store))
    values = {
        "provider_key": "webhook",
        "destination_ref": "operations-primary",
        "event_types": (NotificationEventType.WORKER_READINESS_CRITICAL,),
        "created_by": "operator",
    }

    first, _ = await service.create_subscription(project.id, **values)
    replay, replayed = await service.create_subscription(project.id, **values)

    assert replayed
    assert replay.id == first.id

    with pytest.raises(ResourceConflict, match="different event types"):
        await service.create_subscription(
            project.id,
            **{
                **values,
                "event_types": (NotificationEventType.WORKER_READINESS_ALERTED,),
            },
        )


async def test_scheduled_automatic_retry_can_be_cancelled_idempotently() -> None:
    store = MemoryStore()
    project = Project(
        key="notification-retry-controls",
        name="Notification Retry Controls",
        repository_url="https://example.com/notification-retry-controls.git",
    )
    store.projects[project.id] = project
    delivery = NotificationDelivery(
        subscription_id=project.id,
        project_id=project.id,
        event_id=project.id,
        alert_id=project.id,
        event_type=NotificationEventType.WORKER_READINESS_ALERTED,
        provider_key="webhook",
        destination_ref="ops",
        payload={"message": "alert"},
        idempotency_key="notification:retry-controls",
    )
    store.notification_deliveries[delivery.id] = delivery
    service = NotificationService(lambda: MemoryUnitOfWork(store))
    claimed = await service.claim_next(worker_id="worker-1", provider_key="webhook")
    assert claimed is not None and claimed.lease_token is not None
    await service.fail(
        claimed.id,
        claimed.lease_token,
        "temporary outage",
        code=NotificationFailureCode.PROVIDER_UNAVAILABLE,
        retryable=True,
        automatic_retry_limit=2,
        next_attempt_at=datetime.now(UTC) + timedelta(minutes=1),
    )

    cancelled, replayed = await service.cancel_automatic_retry(
        project.id, delivery.id, requested_by="operator"
    )
    repeated, repeated_replayed = await service.cancel_automatic_retry(
        project.id, delivery.id, requested_by="operator"
    )

    assert not replayed
    assert repeated_replayed
    assert repeated.id == cancelled.id
    assert cancelled.status is NotificationDeliveryStatus.FAILED
    assert cancelled.failure_reason == "temporary outage"
    assert cancelled.failure_retryable is True
    assert cancelled.automatic_retry_limit == 0
    assert cancelled.next_attempt_at is None
    assert store.events[-1].event_type == "notification.delivery_automatic_retry_cancelled"
    assert store.events[-1].payload["actor"] == "operator"
