"""SQLAlchemy persistence for notification subscriptions and deliveries."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.infrastructure.database.models import (
    NotificationDeliveryAttemptRecord,
    NotificationDeliveryRecord,
    NotificationSubscriptionRecord,
)
from jb_orchestrator.notifications import (
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationDeliveryClaim,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationSubscription,
)


def subscription_from_record(record: NotificationSubscriptionRecord) -> NotificationSubscription:
    return NotificationSubscription(
        id=record.id,
        project_id=record.project_id,
        provider_key=record.provider_key,
        destination_ref=record.destination_ref,
        event_types=tuple(NotificationEventType(value) for value in record.event_types),
        enabled=record.enabled,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def delivery_from_record(record: NotificationDeliveryRecord) -> NotificationDelivery:
    return NotificationDelivery(
        id=record.id,
        subscription_id=record.subscription_id,
        project_id=record.project_id,
        event_id=record.event_id,
        alert_id=record.alert_id,
        event_type=record.event_type,
        provider_key=record.provider_key,
        destination_ref=record.destination_ref,
        payload=record.payload,
        idempotency_key=record.idempotency_key,
        status=record.status,
        worker_id=record.worker_id,
        lease_token=record.lease_token,
        lease_expires_at=record.lease_expires_at,
        result=record.result,
        failure_reason=record.failure_reason,
        failure_code=record.failure_code,
        failure_retryable=record.failure_retryable,
        attempt_count=record.attempt_count,
        automatic_retry_limit=record.automatic_retry_limit,
        next_attempt_at=record.next_attempt_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


def attempt_from_record(record: NotificationDeliveryAttemptRecord) -> NotificationDeliveryAttempt:
    return NotificationDeliveryAttempt(
        id=record.id,
        delivery_id=record.delivery_id,
        attempt_number=record.attempt_number,
        trigger=record.trigger,
        worker_id=record.worker_id,
        lease_token=record.lease_token,
        status=record.status,
        result=record.result,
        failure_reason=record.failure_reason,
        failure_code=record.failure_code,
        failure_retryable=record.failure_retryable,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


class SqlAlchemyNotificationSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_add(self, subscription: NotificationSubscription) -> bool:
        values = self._values(subscription)
        dialect_name = self._session.get_bind().dialect.name
        if dialect_name == "postgresql":
            inserted_id = await self._session.scalar(
                postgresql_insert(NotificationSubscriptionRecord)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=["project_id", "provider_key", "destination_ref"]
                )
                .returning(NotificationSubscriptionRecord.id)
            )
        elif dialect_name == "sqlite":
            inserted_id = await self._session.scalar(
                sqlite_insert(NotificationSubscriptionRecord)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=["project_id", "provider_key", "destination_ref"]
                )
                .returning(NotificationSubscriptionRecord.id)
            )
        else:
            raise RuntimeError(f"unsupported notification database: {dialect_name}")
        return inserted_id is not None

    async def get(
        self, subscription_id: UUID, *, for_update: bool = False
    ) -> NotificationSubscription | None:
        statement = select(NotificationSubscriptionRecord).where(
            NotificationSubscriptionRecord.id == subscription_id
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = await self._session.scalar(statement)
        return subscription_from_record(record) if record is not None else None

    async def get_destination(
        self, project_id: UUID, provider_key: str, destination_ref: str
    ) -> NotificationSubscription | None:
        record = await self._session.scalar(
            select(NotificationSubscriptionRecord).where(
                NotificationSubscriptionRecord.project_id == project_id,
                NotificationSubscriptionRecord.provider_key == provider_key,
                NotificationSubscriptionRecord.destination_ref == destination_ref,
            )
        )
        return subscription_from_record(record) if record is not None else None

    async def list_by_project(
        self, project_id: UUID, *, enabled: bool | None = None, limit: int = 100
    ) -> list[NotificationSubscription]:
        statement = select(NotificationSubscriptionRecord).where(
            NotificationSubscriptionRecord.project_id == project_id
        )
        if enabled is not None:
            statement = statement.where(NotificationSubscriptionRecord.enabled.is_(enabled))
        records = await self._session.scalars(
            statement.order_by(
                NotificationSubscriptionRecord.created_at.desc(),
                NotificationSubscriptionRecord.id,
            ).limit(limit)
        )
        return [subscription_from_record(record) for record in records]

    async def save(self, subscription: NotificationSubscription) -> None:
        record = await self._session.get(NotificationSubscriptionRecord, subscription.id)
        if record is None:
            raise LookupError(f"notification subscription not found: {subscription.id}")
        for key, value in self._values(subscription).items():
            if key != "id":
                setattr(record, key, value)

    @staticmethod
    def _values(subscription: NotificationSubscription) -> dict[str, object]:
        return {
            "id": subscription.id,
            "project_id": subscription.project_id,
            "provider_key": subscription.provider_key,
            "destination_ref": subscription.destination_ref,
            "event_types": [value.value for value in subscription.event_types],
            "enabled": subscription.enabled,
            "created_by": subscription.created_by,
            "created_at": subscription.created_at,
            "updated_at": subscription.updated_at,
        }


class SqlAlchemyNotificationDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def try_add(self, delivery: NotificationDelivery) -> bool:
        values = self._values(delivery)
        dialect_name = self._session.get_bind().dialect.name
        if dialect_name == "postgresql":
            inserted_id = await self._session.scalar(
                postgresql_insert(NotificationDeliveryRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["subscription_id", "event_id"])
                .returning(NotificationDeliveryRecord.id)
            )
        elif dialect_name == "sqlite":
            inserted_id = await self._session.scalar(
                sqlite_insert(NotificationDeliveryRecord)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["subscription_id", "event_id"])
                .returning(NotificationDeliveryRecord.id)
            )
        else:
            raise RuntimeError(f"unsupported notification database: {dialect_name}")
        return inserted_id is not None

    async def get(
        self, delivery_id: UUID, *, for_update: bool = False
    ) -> NotificationDelivery | None:
        statement = select(NotificationDeliveryRecord).where(
            NotificationDeliveryRecord.id == delivery_id
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = await self._session.scalar(statement)
        return delivery_from_record(record) if record is not None else None

    async def claim_next(
        self, *, worker_id: str, provider_key: str, lease_seconds: int
    ) -> NotificationDeliveryClaim | None:
        now = datetime.now(UTC)
        record = await self._session.scalar(
            select(NotificationDeliveryRecord)
            .where(
                NotificationDeliveryRecord.provider_key == provider_key,
                or_(
                    NotificationDeliveryRecord.status == NotificationDeliveryStatus.PENDING,
                    (
                        (NotificationDeliveryRecord.status == NotificationDeliveryStatus.CLAIMED)
                        & (NotificationDeliveryRecord.lease_expires_at <= now)
                    ),
                    (
                        (NotificationDeliveryRecord.status == NotificationDeliveryStatus.FAILED)
                        & (NotificationDeliveryRecord.failure_retryable.is_(True))
                        & (NotificationDeliveryRecord.next_attempt_at.is_not(None))
                        & (NotificationDeliveryRecord.next_attempt_at <= now)
                        & (
                            NotificationDeliveryRecord.attempt_count
                            <= NotificationDeliveryRecord.automatic_retry_limit
                        )
                    ),
                ),
            )
            .order_by(NotificationDeliveryRecord.created_at, NotificationDeliveryRecord.id)
            .limit(1)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if record is None:
            return None
        delivery = delivery_from_record(record)
        trigger = delivery.claim(worker_id, lease_seconds=lease_seconds, at=now)
        self._update(record, delivery)
        return NotificationDeliveryClaim(delivery=delivery, trigger=trigger)

    async def list_by_project(
        self,
        project_id: UUID,
        *,
        status: NotificationDeliveryStatus | None = None,
        limit: int = 100,
    ) -> list[NotificationDelivery]:
        statement = select(NotificationDeliveryRecord).where(
            NotificationDeliveryRecord.project_id == project_id
        )
        if status is not None:
            statement = statement.where(NotificationDeliveryRecord.status == status)
        records = await self._session.scalars(
            statement.order_by(
                NotificationDeliveryRecord.created_at.desc(),
                NotificationDeliveryRecord.id,
            ).limit(limit)
        )
        return [delivery_from_record(record) for record in records]

    async def save(self, delivery: NotificationDelivery) -> None:
        record = await self._session.get(NotificationDeliveryRecord, delivery.id)
        if record is None:
            raise LookupError(f"notification delivery not found: {delivery.id}")
        self._update(record, delivery)

    @staticmethod
    def _values(delivery: NotificationDelivery) -> dict[str, object]:
        return {
            "id": delivery.id,
            "subscription_id": delivery.subscription_id,
            "project_id": delivery.project_id,
            "event_id": delivery.event_id,
            "alert_id": delivery.alert_id,
            "event_type": delivery.event_type.value,
            "provider_key": delivery.provider_key,
            "destination_ref": delivery.destination_ref,
            "payload": delivery.payload,
            "idempotency_key": delivery.idempotency_key,
            "status": delivery.status,
            "worker_id": delivery.worker_id,
            "lease_token": delivery.lease_token,
            "lease_expires_at": delivery.lease_expires_at,
            "result": delivery.result,
            "failure_reason": delivery.failure_reason,
            "failure_code": delivery.failure_code,
            "failure_retryable": delivery.failure_retryable,
            "attempt_count": delivery.attempt_count,
            "automatic_retry_limit": delivery.automatic_retry_limit,
            "next_attempt_at": delivery.next_attempt_at,
            "created_at": delivery.created_at,
            "updated_at": delivery.updated_at,
            "completed_at": delivery.completed_at,
        }

    @classmethod
    def _update(cls, record: NotificationDeliveryRecord, delivery: NotificationDelivery) -> None:
        for key, value in cls._values(delivery).items():
            if key != "id":
                setattr(record, key, value)


class SqlAlchemyNotificationDeliveryAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, attempt: NotificationDeliveryAttempt) -> None:
        self._session.add(NotificationDeliveryAttemptRecord(**self._values(attempt)))

    async def get(
        self, delivery_id: UUID, attempt_number: int, *, for_update: bool = False
    ) -> NotificationDeliveryAttempt | None:
        statement = select(NotificationDeliveryAttemptRecord).where(
            NotificationDeliveryAttemptRecord.delivery_id == delivery_id,
            NotificationDeliveryAttemptRecord.attempt_number == attempt_number,
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = await self._session.scalar(statement)
        return attempt_from_record(record) if record is not None else None

    async def list_for_delivery(
        self, delivery_id: UUID, *, limit: int = 100
    ) -> list[NotificationDeliveryAttempt]:
        records = await self._session.scalars(
            select(NotificationDeliveryAttemptRecord)
            .where(NotificationDeliveryAttemptRecord.delivery_id == delivery_id)
            .order_by(NotificationDeliveryAttemptRecord.attempt_number.desc())
            .limit(limit)
        )
        return [attempt_from_record(record) for record in records]

    async def save(self, attempt: NotificationDeliveryAttempt) -> None:
        record = await self._session.get(NotificationDeliveryAttemptRecord, attempt.id)
        if record is None:
            raise LookupError(f"notification delivery attempt not found: {attempt.id}")
        for key, value in self._values(attempt).items():
            if key != "id":
                setattr(record, key, value)

    @staticmethod
    def _values(attempt: NotificationDeliveryAttempt) -> dict[str, object]:
        return {
            "id": attempt.id,
            "delivery_id": attempt.delivery_id,
            "attempt_number": attempt.attempt_number,
            "trigger": attempt.trigger,
            "worker_id": attempt.worker_id,
            "lease_token": attempt.lease_token,
            "status": attempt.status,
            "result": attempt.result,
            "failure_reason": attempt.failure_reason,
            "failure_code": attempt.failure_code,
            "failure_retryable": attempt.failure_retryable,
            "started_at": attempt.started_at,
            "finished_at": attempt.finished_at,
        }
