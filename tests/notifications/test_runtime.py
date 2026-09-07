from datetime import UTC, datetime, timedelta
from uuid import uuid4

from jb_orchestrator.application import NotificationService
from jb_orchestrator.domain import Project
from jb_orchestrator.notifications import (
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationFailureCode,
    NotificationProviderFailure,
    NotificationRequest,
    NotificationResult,
)
from jb_orchestrator.notifications.registry import NotificationProviderRegistry
from jb_orchestrator.notifications.runtime import NotificationRuntime
from tests.support import MemoryStore, MemoryUnitOfWork


class Provider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[NotificationRequest] = []

    async def deliver(self, request: NotificationRequest) -> NotificationResult:
        self.requests.append(request)
        if self.fail:
            raise NotificationProviderFailure(
                "temporarily unavailable",
                code=NotificationFailureCode.PROVIDER_UNAVAILABLE,
            )
        return NotificationResult(output={"message_id": "message-1"})


def add_delivery(store: MemoryStore) -> NotificationDelivery:
    item = NotificationDelivery(
        subscription_id=uuid4(),
        project_id=uuid4(),
        event_id=uuid4(),
        alert_id=uuid4(),
        event_type=NotificationEventType.WORKER_READINESS_CRITICAL,
        provider_key="fixture",
        destination_ref="ops",
        payload={"severity": "critical"},
        idempotency_key=f"notification:{uuid4()}",
    )
    store.notification_deliveries[item.id] = item
    return item


async def test_runtime_delivers_and_records_provider_evidence() -> None:
    store = MemoryStore()
    item = add_delivery(store)
    provider = Provider()
    runtime = NotificationRuntime(
        "notification-worker",
        NotificationService(lambda: MemoryUnitOfWork(store)),
        NotificationProviderRegistry({"fixture": provider}),
        lease_seconds=10,
        delivery_timeout_seconds=5,
    )

    assert await runtime.run_once() is True
    assert item.status is NotificationDeliveryStatus.SUCCEEDED
    assert item.result == {"message_id": "message-1"}
    assert provider.requests[0].idempotency_key == item.idempotency_key
    [attempt] = store.notification_delivery_attempts.values()
    assert attempt.status.value == "succeeded"
    assert attempt.result == {"message_id": "message-1"}


async def test_runtime_records_typed_provider_failure() -> None:
    store = MemoryStore()
    item = add_delivery(store)
    runtime = NotificationRuntime(
        "notification-worker",
        NotificationService(lambda: MemoryUnitOfWork(store)),
        NotificationProviderRegistry({"fixture": Provider(fail=True)}),
        lease_seconds=10,
        delivery_timeout_seconds=5,
    )

    assert await runtime.run_once() is True
    assert item.status is NotificationDeliveryStatus.FAILED
    assert item.failure_code is NotificationFailureCode.PROVIDER_UNAVAILABLE
    [attempt] = store.notification_delivery_attempts.values()
    assert attempt.status.value == "failed"
    assert attempt.failure_code is NotificationFailureCode.PROVIDER_UNAVAILABLE


async def test_failed_delivery_can_be_manually_retried_with_original_payload() -> None:
    store = MemoryStore()
    item = add_delivery(store)
    store.projects[item.project_id] = Project(
        id=item.project_id,
        key="notification-retry",
        name="Notification Retry",
        repository_url="https://example.com/notification-retry.git",
    )
    service = NotificationService(lambda: MemoryUnitOfWork(store))
    failing_runtime = NotificationRuntime(
        "notification-worker-1",
        service,
        NotificationProviderRegistry({"fixture": Provider(fail=True)}),
        lease_seconds=10,
        delivery_timeout_seconds=5,
    )
    original_payload = item.payload
    original_key = item.idempotency_key
    await failing_runtime.run_once()

    retried, replayed = await service.retry(item.project_id, item.id, requested_by="operator")
    assert replayed is False
    assert retried.status is NotificationDeliveryStatus.PENDING
    assert retried.payload == original_payload
    assert retried.idempotency_key == original_key

    successful_runtime = NotificationRuntime(
        "notification-worker-2",
        service,
        NotificationProviderRegistry({"fixture": Provider()}),
        lease_seconds=10,
        delivery_timeout_seconds=5,
    )
    await successful_runtime.run_once()

    attempts = await service.list_attempts(item.project_id, item.id)
    assert [attempt.trigger.value for attempt in attempts] == ["manual", "initial"]
    assert [attempt.status.value for attempt in attempts] == ["succeeded", "failed"]
    assert item.attempt_count == 2


async def test_expired_claim_closes_previous_attempt_before_recovery() -> None:
    store = MemoryStore()
    item = add_delivery(store)
    service = NotificationService(lambda: MemoryUnitOfWork(store))
    first = await service.claim_next(
        worker_id="notification-worker-1", provider_key="fixture", lease_seconds=10
    )
    assert first is not None
    item.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    recovered = await service.claim_next(
        worker_id="notification-worker-2", provider_key="fixture", lease_seconds=10
    )

    assert recovered is not None
    attempts = sorted(
        store.notification_delivery_attempts.values(), key=lambda value: value.attempt_number
    )
    assert attempts[0].status.value == "failed"
    assert attempts[0].failure_code is NotificationFailureCode.LEASE_EXPIRED
    assert attempts[1].trigger.value == "lease_recovery"
    assert attempts[1].status.value == "claimed"
