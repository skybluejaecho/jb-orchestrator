from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from jb_orchestrator.domain import InvalidStateTransition
from jb_orchestrator.notifications import (
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationFailureCode,
)


def delivery() -> NotificationDelivery:
    return NotificationDelivery(
        subscription_id=uuid4(),
        project_id=uuid4(),
        event_id=uuid4(),
        alert_id=uuid4(),
        event_type=NotificationEventType.WORKER_READINESS_ALERTED,
        provider_key="test",
        destination_ref="team",
        payload={"message": "alert"},
        idempotency_key=f"notification:{uuid4()}",
    )


def test_claim_and_succeed_require_current_lease() -> None:
    item = delivery()
    item.claim("worker-1", lease_seconds=30)
    assert item.status is NotificationDeliveryStatus.CLAIMED
    assert item.attempt_count == 1
    assert item.lease_token is not None

    with pytest.raises(InvalidStateTransition):
        item.succeed(uuid4(), {"message_id": "wrong"})

    item.succeed(item.lease_token, {"message_id": "ok"})
    assert item.status is NotificationDeliveryStatus.SUCCEEDED
    assert item.result == {"message_id": "ok"}
    assert item.completed_at is not None


def test_expired_claim_can_be_recovered_with_a_new_lease() -> None:
    item = delivery()
    started_at = datetime(2026, 9, 7, tzinfo=UTC)
    item.claim("worker-1", lease_seconds=10, at=started_at)
    stale_token = item.lease_token

    item.claim("worker-2", lease_seconds=10, at=started_at + timedelta(seconds=11))

    assert item.worker_id == "worker-2"
    assert item.lease_token != stale_token
    assert item.attempt_count == 2


def test_failed_delivery_is_terminal() -> None:
    item = delivery()
    item.claim("worker-1", lease_seconds=30)
    assert item.lease_token is not None
    item.fail(
        item.lease_token,
        "provider unavailable",
        code=NotificationFailureCode.PROVIDER_UNAVAILABLE,
    )
    assert item.status is NotificationDeliveryStatus.FAILED
    assert item.failure_code is NotificationFailureCode.PROVIDER_UNAVAILABLE
    with pytest.raises(InvalidStateTransition):
        item.claim("worker-2", lease_seconds=30)
