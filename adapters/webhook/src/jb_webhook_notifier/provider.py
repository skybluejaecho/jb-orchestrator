"""Generic JSON Webhook implementation of the notification provider port."""

import hashlib
import hmac
import json
from collections.abc import Mapping
from urllib.parse import urlparse

import httpx

from jb_orchestrator.notifications import (
    NotificationFailureCode,
    NotificationProviderFailure,
    NotificationRequest,
    NotificationResult,
)
from jb_webhook_notifier.settings import WebhookDestinationSettings


class WebhookDeliveryError(NotificationProviderFailure):
    """A safe, provider-neutral failure without endpoint or response-body disclosure."""


class WebhookNotificationProvider:
    def __init__(
        self,
        destinations: Mapping[str, WebhookDestinationSettings],
        *,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_insecure_loopback: bool = False,
    ) -> None:
        if not destinations:
            raise ValueError("Webhook Provider requires at least one destination")
        if timeout_seconds <= 0:
            raise ValueError("Webhook timeout must be positive")
        self._destinations: dict[str, WebhookDestinationSettings] = {}
        for reference, destination in destinations.items():
            normalized = reference.strip()
            if not normalized:
                raise ValueError("Webhook destination reference must not be empty")
            if normalized in self._destinations:
                raise ValueError(f"Webhook destination reference is duplicated: {normalized}")
            self._validate_url(destination.url, allow_insecure_loopback=allow_insecure_loopback)
            if (
                destination.signing_secret is not None
                and not destination.signing_secret.get_secret_value()
            ):
                raise ValueError("Webhook signing secret must not be empty")
            self._destinations[normalized] = destination
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def deliver(self, request: NotificationRequest) -> NotificationResult:
        try:
            destination = self._destinations[request.destination_ref]
        except KeyError as exc:
            raise WebhookDeliveryError(
                "Webhook destination reference is not configured",
                code=NotificationFailureCode.PROVIDER_REJECTED,
            ) from exc
        body = self._body(request)
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": request.idempotency_key,
            "User-Agent": "jb-orchestrator-webhook-notifier",
            "X-JB-Delivery-ID": str(request.delivery_id),
            "X-JB-Event-Type": request.event_type.value,
        }
        if destination.signing_secret is not None:
            digest = hmac.new(
                destination.signing_secret.get_secret_value().encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
            headers["X-JB-Signature-256"] = f"sha256={digest}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(destination.url.strip(), content=body, headers=headers)
        except httpx.TransportError as exc:
            raise WebhookDeliveryError(
                f"Webhook transport failed: {type(exc).__name__}",
                code=NotificationFailureCode.PROVIDER_UNAVAILABLE,
            ) from exc
        if not 200 <= response.status_code < 300:
            unavailable = response.status_code in {408, 429} or response.status_code >= 500
            raise WebhookDeliveryError(
                f"Webhook returned HTTP {response.status_code}",
                code=(
                    NotificationFailureCode.PROVIDER_UNAVAILABLE
                    if unavailable
                    else NotificationFailureCode.PROVIDER_REJECTED
                ),
            )
        request_id = response.headers.get("x-request-id")
        output: dict[str, object] = {"status_code": response.status_code}
        if request_id:
            output["request_id"] = request_id[:255]
        return NotificationResult(output=output)

    @staticmethod
    def _body(request: NotificationRequest) -> bytes:
        envelope = {
            "delivery_id": str(request.delivery_id),
            "event_type": request.event_type.value,
            "idempotency_key": request.idempotency_key,
            "payload": request.payload,
            "project_id": str(request.project_id),
        }
        return json.dumps(
            envelope,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()

    @staticmethod
    def _validate_url(value: str, *, allow_insecure_loopback: bool) -> None:
        parsed = urlparse(value.strip())
        insecure_loopback = (
            allow_insecure_loopback
            and parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        )
        if parsed.scheme != "https" and not insecure_loopback:
            raise ValueError("Webhook destination must use HTTPS, except test-only loopback HTTP")
        if not parsed.hostname:
            raise ValueError("Webhook destination requires a valid hostname")
