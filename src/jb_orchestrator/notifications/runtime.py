"""Lease-bounded runtime for durable notification deliveries."""

import asyncio
import math
from datetime import UTC, datetime, timedelta

from jb_orchestrator.application import NotificationService
from jb_orchestrator.notifications.models import (
    MAX_AUTOMATIC_RETRY_LIMIT,
    NotificationDelivery,
    NotificationFailureCode,
    NotificationProviderFailure,
    NotificationRequest,
)
from jb_orchestrator.notifications.registry import NotificationProviderRegistry


class NotificationRuntime:
    def __init__(
        self,
        worker_id: str,
        notifications: NotificationService,
        providers: NotificationProviderRegistry,
        *,
        poll_interval_seconds: float = 1.0,
        lease_seconds: int = 60,
        delivery_timeout_seconds: float = 30.0,
        automatic_retry_limit: int = 0,
        automatic_retry_base_delay_seconds: float = 30.0,
        automatic_retry_max_delay_seconds: float = 300.0,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("notification worker id must not be empty")
        if not providers.supported_keys:
            raise ValueError("notification worker requires at least one provider")
        if poll_interval_seconds <= 0 or lease_seconds <= 0 or delivery_timeout_seconds <= 0:
            raise ValueError("notification worker intervals must be positive")
        if delivery_timeout_seconds >= lease_seconds:
            raise ValueError("notification delivery timeout must be shorter than its lease")
        if not 0 <= automatic_retry_limit <= MAX_AUTOMATIC_RETRY_LIMIT:
            raise ValueError(
                "notification automatic retry limit must be between 0 and "
                f"{MAX_AUTOMATIC_RETRY_LIMIT}"
            )
        if automatic_retry_base_delay_seconds <= 0 or automatic_retry_max_delay_seconds <= 0:
            raise ValueError("notification automatic retry delays must be positive")
        if automatic_retry_base_delay_seconds > automatic_retry_max_delay_seconds:
            raise ValueError("notification retry base delay must not exceed maximum delay")
        self._worker_id = worker_id.strip()
        self._notifications = notifications
        self._providers = providers
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._delivery_timeout_seconds = delivery_timeout_seconds
        self._automatic_retry_limit = automatic_retry_limit
        self._automatic_retry_base_delay_seconds = automatic_retry_base_delay_seconds
        self._automatic_retry_max_delay_seconds = automatic_retry_max_delay_seconds

    async def run_once(self) -> bool:
        delivery = await self._claim_next()
        if delivery is None:
            return False
        lease_token = delivery.lease_token
        if lease_token is None:  # pragma: no cover - repository contract
            raise RuntimeError("claimed notification delivery has no lease token")
        request = NotificationRequest(
            delivery_id=delivery.id,
            project_id=delivery.project_id,
            event_type=delivery.event_type,
            destination_ref=delivery.destination_ref,
            payload=delivery.payload,
            idempotency_key=delivery.idempotency_key,
        )
        try:
            result = await asyncio.wait_for(
                self._providers.deliver(delivery.provider_key, request),
                timeout=self._delivery_timeout_seconds,
            )
        except Exception as exc:
            code = self._failure_code(exc)
            retryable = code in {
                NotificationFailureCode.PROVIDER_UNAVAILABLE,
                NotificationFailureCode.TIMEOUT,
            }
            await self._notifications.fail(
                delivery.id,
                lease_token,
                str(exc) or type(exc).__name__,
                code=code,
                retryable=retryable,
                automatic_retry_limit=self._automatic_retry_limit,
                next_attempt_at=self._next_attempt_at(delivery) if retryable else None,
            )
        else:
            await self._notifications.succeed(delivery.id, lease_token, result.output)
        return True

    async def run(self) -> None:
        while True:
            if not await self.run_once():
                await asyncio.sleep(self._poll_interval_seconds)

    async def _claim_next(self) -> NotificationDelivery | None:
        for provider_key in sorted(self._providers.supported_keys):
            delivery = await self._notifications.claim_next(
                worker_id=self._worker_id,
                provider_key=provider_key,
                lease_seconds=self._lease_seconds,
            )
            if delivery is not None:
                return delivery
        return None

    @staticmethod
    def _failure_code(exc: Exception) -> NotificationFailureCode:
        if isinstance(exc, NotificationProviderFailure):
            return exc.code
        if isinstance(exc, TimeoutError):
            return NotificationFailureCode.TIMEOUT
        return NotificationFailureCode.UNEXPECTED

    def _next_attempt_at(self, delivery: NotificationDelivery) -> datetime | None:
        if self._automatic_retry_limit == 0:
            return None
        if delivery.attempt_count > self._automatic_retry_limit:
            return None
        exponent = delivery.attempt_count - 1
        ratio = self._automatic_retry_max_delay_seconds / self._automatic_retry_base_delay_seconds
        steps_to_cap = max(0, math.ceil(math.log2(ratio)))
        delay = min(
            self._automatic_retry_base_delay_seconds * (2 ** min(exponent, steps_to_cap)),
            self._automatic_retry_max_delay_seconds,
        )
        return datetime.now(UTC) + timedelta(seconds=delay)
