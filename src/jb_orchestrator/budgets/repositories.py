"""Persistence ports for project budgets and usage accounting."""

from typing import Protocol
from uuid import UUID

from jb_orchestrator.budgets.models import BudgetAccount, BudgetReservation, UsageRecord


class BudgetAccountRepository(Protocol):
    async def add(self, account: BudgetAccount) -> None: ...

    async def get_by_project(
        self, project_id: UUID, *, for_update: bool = False
    ) -> BudgetAccount | None: ...

    async def save(self, account: BudgetAccount) -> None: ...


class BudgetReservationRepository(Protocol):
    async def add(self, reservation: BudgetReservation) -> None: ...

    async def get_by_key(
        self, idempotency_key: str, *, for_update: bool = False
    ) -> BudgetReservation | None: ...

    async def list_reserved_by_run(
        self, run_id: UUID, *, for_update: bool = False
    ) -> list[BudgetReservation]: ...

    async def save(self, reservation: BudgetReservation) -> None: ...


class UsageRecordRepository(Protocol):
    async def add(self, record: UsageRecord) -> None: ...

    async def get_by_reservation(self, reservation_id: UUID) -> UsageRecord | None: ...

    async def list_by_project(self, project_id: UUID) -> list[UsageRecord]: ...
