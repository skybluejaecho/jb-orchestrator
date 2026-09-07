import hashlib
import hmac
import json
from uuid import UUID

import httpx
import pytest
from jb_webhook_notifier.provider import WebhookDeliveryError, WebhookNotificationProvider
from jb_webhook_notifier.settings import WebhookDestinationSettings
from pydantic import SecretStr

from jb_orchestrator.notifications import (
    NotificationEventType,
    NotificationFailureCode,
    NotificationRequest,
)


def request(*, destination_ref: str = "ops") -> NotificationRequest:
    return NotificationRequest(
        delivery_id=UUID("10000000-0000-0000-0000-000000000001"),
        project_id=UUID("20000000-0000-0000-0000-000000000002"),
        event_type=NotificationEventType.WORKER_READINESS_ALERTED,
        destination_ref=destination_ref,
        payload={"message": "작업자 없음"},
        idempotency_key="notification:test:1",
    )


def destination(*, secret: str | None = None) -> WebhookDestinationSettings:
    return WebhookDestinationSettings(
        url="https://hooks.example.test/events",
        signing_secret=SecretStr(secret) if secret is not None else None,
    )


async def test_provider_posts_canonical_signed_envelope() -> None:
    received: list[httpx.Request] = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        received.append(http_request)
        return httpx.Response(202, headers={"x-request-id": "remote-1"})

    provider = WebhookNotificationProvider(
        {"ops": destination(secret="signing-secret")},
        transport=httpx.MockTransport(handler),
    )

    result = await provider.deliver(request())

    assert result.output == {"status_code": 202, "request_id": "remote-1"}
    [sent] = received
    envelope = json.loads(sent.content)
    assert envelope["payload"] == {"message": "작업자 없음"}
    assert sent.headers["Idempotency-Key"] == "notification:test:1"
    assert sent.headers["X-JB-Event-Type"] == "worker.readiness_alerted"
    expected = hmac.new(b"signing-secret", sent.content, hashlib.sha256).hexdigest()
    assert sent.headers["X-JB-Signature-256"] == f"sha256={expected}"


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (400, NotificationFailureCode.PROVIDER_REJECTED),
        (429, NotificationFailureCode.PROVIDER_UNAVAILABLE),
        (503, NotificationFailureCode.PROVIDER_UNAVAILABLE),
    ],
)
async def test_provider_classifies_http_failures(
    status_code: int, code: NotificationFailureCode
) -> None:
    provider = WebhookNotificationProvider(
        {"ops": destination()},
        transport=httpx.MockTransport(lambda request: httpx.Response(status_code)),
    )

    with pytest.raises(WebhookDeliveryError) as error:
        await provider.deliver(request())

    assert error.value.code is code


async def test_provider_rejects_unknown_reference_without_disclosing_destinations() -> None:
    provider = WebhookNotificationProvider({"ops-secret-name": destination()})
    with pytest.raises(WebhookDeliveryError, match="not configured") as error:
        await provider.deliver(request(destination_ref="missing"))
    assert "ops-secret-name" not in str(error.value)


async def test_provider_hides_response_body_and_classifies_transport_failure() -> None:
    rejected = WebhookNotificationProvider(
        {"ops": destination()},
        transport=httpx.MockTransport(
            lambda request: httpx.Response(400, text="remote-secret-detail")
        ),
    )
    with pytest.raises(WebhookDeliveryError) as response_error:
        await rejected.deliver(request())
    assert "remote-secret-detail" not in str(response_error.value)

    def fail_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("endpoint detail", request=request)

    unavailable = WebhookNotificationProvider(
        {"ops": destination()}, transport=httpx.MockTransport(fail_transport)
    )
    with pytest.raises(WebhookDeliveryError) as transport_error:
        await unavailable.deliver(request())
    assert transport_error.value.code is NotificationFailureCode.PROVIDER_UNAVAILABLE
    assert "endpoint detail" not in str(transport_error.value)


def test_provider_requires_https_except_explicit_test_loopback() -> None:
    insecure = WebhookDestinationSettings(url="http://example.test/events")
    with pytest.raises(ValueError, match="HTTPS"):
        WebhookNotificationProvider({"ops": insecure})

    loopback = WebhookDestinationSettings(url="http://127.0.0.1:9876/events")
    WebhookNotificationProvider({"ops": loopback}, allow_insecure_loopback=True)


def test_provider_rejects_ambiguous_reference_and_empty_secret() -> None:
    with pytest.raises(ValueError, match="duplicated"):
        WebhookNotificationProvider({"ops": destination(), " ops ": destination()})
    with pytest.raises(ValueError, match="secret must not be empty"):
        WebhookNotificationProvider({"ops": destination(secret="")})
