"""Installed Webhook Provider entry-point factory."""

import os

from jb_orchestrator.notifications import NotificationProvider
from jb_webhook_notifier.provider import WebhookNotificationProvider
from jb_webhook_notifier.settings import WebhookProviderSettings


class WebhookProviderConfigurationError(ValueError):
    """Required adapter-owned destination configuration is missing or unsafe."""


def create_provider() -> NotificationProvider:
    settings = WebhookProviderSettings()
    if not settings.destinations:
        raise WebhookProviderConfigurationError("JB_WEBHOOK_DESTINATIONS is required")
    if settings.allow_insecure_loopback and os.environ.get("JB_ENVIRONMENT") != "test":
        raise WebhookProviderConfigurationError(
            "JB_WEBHOOK_ALLOW_INSECURE_LOOPBACK requires JB_ENVIRONMENT=test"
        )
    return WebhookNotificationProvider(
        settings.destinations,
        timeout_seconds=settings.http_timeout_seconds,
        allow_insecure_loopback=settings.allow_insecure_loopback,
    )
