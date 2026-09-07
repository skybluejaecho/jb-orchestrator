"""Notification domain models and persistence contracts."""

from jb_orchestrator.notifications.models import (
    NotificationAttemptStatus,
    NotificationAttemptTrigger,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationDeliveryClaim,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationFailureCode,
    NotificationProvider,
    NotificationProviderFailure,
    NotificationRequest,
    NotificationResult,
    NotificationSubscription,
)
from jb_orchestrator.notifications.registry import (
    NOTIFICATION_PROVIDER_ENTRY_POINT_GROUP,
    NotificationProviderNotFoundError,
    NotificationProviderRegistrationError,
    NotificationProviderRegistry,
)
from jb_orchestrator.notifications.repositories import (
    NotificationDeliveryAttemptRepository,
    NotificationDeliveryRepository,
    NotificationSubscriptionRepository,
)

__all__ = [
    "NOTIFICATION_PROVIDER_ENTRY_POINT_GROUP",
    "NotificationAttemptStatus",
    "NotificationAttemptTrigger",
    "NotificationDelivery",
    "NotificationDeliveryAttempt",
    "NotificationDeliveryAttemptRepository",
    "NotificationDeliveryClaim",
    "NotificationDeliveryRepository",
    "NotificationDeliveryStatus",
    "NotificationEventType",
    "NotificationFailureCode",
    "NotificationProvider",
    "NotificationProviderFailure",
    "NotificationProviderNotFoundError",
    "NotificationProviderRegistrationError",
    "NotificationProviderRegistry",
    "NotificationRequest",
    "NotificationResult",
    "NotificationSubscription",
    "NotificationSubscriptionRepository",
]
