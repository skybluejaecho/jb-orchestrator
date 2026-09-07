from uuid import uuid4

from jb_orchestrator.application import NotificationService
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
