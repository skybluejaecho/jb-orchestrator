"""SQLAlchemy adapters for budget accounts, reservations, and usage records."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jb_orchestrator.budgets import (
    BudgetAccount,
    BudgetReservation,
    BudgetReservationStatus,
    UsageRecord,
)
from jb_orchestrator.infrastructure.database.models import (
    BudgetAccountRecord,
    BudgetReservationRecord,
    UsageRecordRecord,
)


def account_from_record(record: BudgetAccountRecord) -> BudgetAccount:
    return BudgetAccount(
        id=record.id,
        project_id=record.project_id,
        limit_usd=record.limit_usd,
        reserved_usd=record.reserved_usd,
        spent_usd=record.spent_usd,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def reservation_from_record(record: BudgetReservationRecord) -> BudgetReservation:
    return BudgetReservation(
        id=record.id,
        account_id=record.account_id,
        project_id=record.project_id,
        run_id=record.run_id,
        execution_id=record.execution_id,
        node_key=record.node_key,
        idempotency_key=record.idempotency_key,
        reserved_usd=record.reserved_usd,
        status=record.status,
        actual_usd=record.actual_usd,
        created_at=record.created_at,
        finalized_at=record.finalized_at,
    )


def usage_from_record(record: UsageRecordRecord) -> UsageRecord:
    return UsageRecord(
        id=record.id,
        reservation_id=record.reservation_id,
        account_id=record.account_id,
        project_id=record.project_id,
        run_id=record.run_id,
        execution_id=record.execution_id,
        node_key=record.node_key,
        kind=record.kind,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        cost_usd=record.cost_usd,
        model_profile_key=record.model_profile_key,
        model_profile_version=record.model_profile_version,
        recorded_at=record.recorded_at,
    )


class SqlAlchemyBudgetAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, account: BudgetAccount) -> None:
        self._session.add(
            BudgetAccountRecord(
                id=account.id,
                project_id=account.project_id,
                limit_usd=account.limit_usd,
                reserved_usd=account.reserved_usd,
                spent_usd=account.spent_usd,
                version=account.version,
                created_at=account.created_at,
                updated_at=account.updated_at,
            )
        )

    async def get_by_project(
        self, project_id: UUID, *, for_update: bool = False
    ) -> BudgetAccount | None:
        statement = select(BudgetAccountRecord).where(BudgetAccountRecord.project_id == project_id)
        if for_update:
            statement = statement.with_for_update()
        record = await self._session.scalar(statement)
        return account_from_record(record) if record is not None else None

    async def save(self, account: BudgetAccount) -> None:
        record = await self._session.get(BudgetAccountRecord, account.id)
        if record is None:
            raise LookupError(f"budget account not found: {account.id}")
        record.limit_usd = account.limit_usd
        record.reserved_usd = account.reserved_usd
        record.spent_usd = account.spent_usd
        record.version = account.version
        record.updated_at = account.updated_at


class SqlAlchemyBudgetReservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, reservation: BudgetReservation) -> None:
        self._session.add(
            BudgetReservationRecord(
                id=reservation.id,
                account_id=reservation.account_id,
                project_id=reservation.project_id,
                run_id=reservation.run_id,
                execution_id=reservation.execution_id,
                node_key=reservation.node_key,
                idempotency_key=reservation.idempotency_key,
                reserved_usd=reservation.reserved_usd,
                status=reservation.status,
                actual_usd=reservation.actual_usd,
                created_at=reservation.created_at,
                finalized_at=reservation.finalized_at,
            )
        )

    async def get_by_key(
        self, idempotency_key: str, *, for_update: bool = False
    ) -> BudgetReservation | None:
        statement = select(BudgetReservationRecord).where(
            BudgetReservationRecord.idempotency_key == idempotency_key
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = await self._session.scalar(statement)
        return reservation_from_record(record) if record is not None else None

    async def list_reserved_by_run(
        self, run_id: UUID, *, for_update: bool = False
    ) -> list[BudgetReservation]:
        statement = select(BudgetReservationRecord).where(
            BudgetReservationRecord.run_id == run_id,
            BudgetReservationRecord.status == BudgetReservationStatus.RESERVED,
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        records = await self._session.scalars(statement)
        return [reservation_from_record(record) for record in records]

    async def save(self, reservation: BudgetReservation) -> None:
        record = await self._session.get(BudgetReservationRecord, reservation.id)
        if record is None:
            raise LookupError(f"budget reservation not found: {reservation.id}")
        record.status = reservation.status
        record.actual_usd = reservation.actual_usd
        record.finalized_at = reservation.finalized_at


class SqlAlchemyUsageRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: UsageRecord) -> None:
        self._session.add(
            UsageRecordRecord(
                id=record.id,
                reservation_id=record.reservation_id,
                account_id=record.account_id,
                project_id=record.project_id,
                run_id=record.run_id,
                execution_id=record.execution_id,
                node_key=record.node_key,
                kind=record.kind,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                cost_usd=record.cost_usd,
                model_profile_key=record.model_profile_key,
                model_profile_version=record.model_profile_version,
                recorded_at=record.recorded_at,
            )
        )

    async def get_by_reservation(self, reservation_id: UUID) -> UsageRecord | None:
        record = await self._session.scalar(
            select(UsageRecordRecord).where(UsageRecordRecord.reservation_id == reservation_id)
        )
        return usage_from_record(record) if record is not None else None

    async def list_by_project(self, project_id: UUID) -> list[UsageRecord]:
        records = await self._session.scalars(
            select(UsageRecordRecord)
            .where(UsageRecordRecord.project_id == project_id)
            .order_by(UsageRecordRecord.recorded_at, UsageRecordRecord.id)
        )
        return [usage_from_record(record) for record in records]
