from uuid import uuid4

import pytest

from jb_orchestrator.domain import DomainValidationError
from jb_orchestrator.notifications import NotificationEventType, NotificationSubscription


def test_subscription_normalizes_provider_and_event_types() -> None:
    subscription = NotificationSubscription(
        project_id=uuid4(),
        provider_key=" WebHook ",
        destination_ref=" operations-primary ",
        event_types=(
            NotificationEventType.WORKER_READINESS_RESOLVED,
            NotificationEventType.WORKER_READINESS_ALERTED,
            NotificationEventType.WORKER_READINESS_ALERTED,
        ),
        created_by="operator",
    )

    assert subscription.provider_key == "webhook"
    assert subscription.destination_ref == "operations-primary"
    assert subscription.event_types == (
        NotificationEventType.WORKER_READINESS_ALERTED,
        NotificationEventType.WORKER_READINESS_RESOLVED,
    )


def test_subscription_rejects_empty_event_selection() -> None:
    with pytest.raises(DomainValidationError, match="requires event types"):
        NotificationSubscription(
            project_id=uuid4(),
            provider_key="webhook",
            destination_ref="operations-primary",
            event_types=(),
            created_by="operator",
        )
