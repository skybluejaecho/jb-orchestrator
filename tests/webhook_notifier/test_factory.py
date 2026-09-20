import json

import pytest
from jb_webhook_notifier.factory import (
    WebhookProviderConfigurationError,
    create_provider,
)
from jb_webhook_notifier.provider import WebhookNotificationProvider


def test_factory_requires_destination_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JB_WEBHOOK_DESTINATIONS", raising=False)
    with pytest.raises(WebhookProviderConfigurationError, match="DESTINATIONS"):
        create_provider()


def test_factory_builds_provider_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "JB_WEBHOOK_DESTINATIONS",
        json.dumps({"ops": {"url": "https://hooks.example.test/events"}}),
    )
    assert isinstance(create_provider(), WebhookNotificationProvider)


def test_factory_rejects_insecure_mode_outside_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JB_ENVIRONMENT", "local")
    monkeypatch.setenv(
        "JB_WEBHOOK_DESTINATIONS",
        json.dumps({"ops": {"url": "http://127.0.0.1:9876/events"}}),
    )
    monkeypatch.setenv("JB_WEBHOOK_ALLOW_INSECURE_LOOPBACK", "true")
    with pytest.raises(WebhookProviderConfigurationError, match="JB_ENVIRONMENT=test"):
        create_provider()
