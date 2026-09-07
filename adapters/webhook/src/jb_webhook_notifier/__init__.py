"""Installable generic JSON webhook notification provider."""

from jb_webhook_notifier.factory import create_provider
from jb_webhook_notifier.provider import WebhookNotificationProvider

__all__ = ["WebhookNotificationProvider", "create_provider"]
