"""Transactional project budget reservation and usage settlement."""

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.budgets import (
    BudgetAccount,
    BudgetReservation,
    BudgetReservationStatus,
    UsageKind,
    UsageRecord,
    money,
)
from jb_orchestrator.domain import DomainEvent
from jb_orchestrator.worker.models import TaskClaim, TokenUsage

_MILLION = Decimal(1_000_000)


class BudgetUsageRequired(RuntimeError):
    """A model-backed executor omitted required token usage."""


async def release_run_reservations(unit_of_work: UnitOfWork, run_id: UUID, *, reason: str) -> int:
    """Release every active reservation for a terminally cancelled run."""

    reservations = await unit_of_work.budget_reservations.list_reserved_by_run(run_id)
    if not reservations:
        return 0
    project_id = reservations[0].project_id
    account = await unit_of_work.budget_accounts.get_by_project(project_id, for_update=True)
    if account is None:
        raise ResourceNotFound(f"budget account not found for reserved run: {run_id}")
    reservations = await unit_of_work.budget_reservations.list_reserved_by_run(
        run_id, for_update=True
    )
    for reservation in reservations:
        if reservation.project_id != project_id:
            raise RuntimeError(f"run has reservations from multiple projects: {run_id}")
        account.release(reservation.reserved_usd)
        reservation.release()
        await unit_of_work.budget_reservations.save(reservation)
        await unit_of_work.events.append(
            DomainEvent(
                aggregate_type="budget_reservation",
                aggregate_id=reservation.id,
                event_type="budget.released",
                payload={"run_id": str(run_id), "reason": reason},
            )
        )
    await unit_of_work.budget_accounts.save(account)
    return len(reservations)


class BudgetService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def configure(self, project_id: UUID, limit_usd: Decimal) -> BudgetAccount:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.projects.get(project_id) is None:
                raise ResourceNotFound(f"project not found: {project_id}")
            account = await unit_of_work.budget_accounts.get_by_project(project_id, for_update=True)
            event_type = "budget.configured"
            if account is None:
                account = BudgetAccount(project_id=project_id, limit_usd=limit_usd)
                await unit_of_work.budget_accounts.add(account)
            else:
                account.set_limit(limit_usd)
                await unit_of_work.budget_accounts.save(account)
                event_type = "budget.limit_changed"
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="budget_account",
                    aggregate_id=account.id,
                    event_type=event_type,
                    payload={"project_id": str(project_id), "limit_usd": str(account.limit_usd)},
                )
            )
            await unit_of_work.commit()
        return account

    async def get(self, project_id: UUID) -> BudgetAccount:
        async with self._unit_of_work_factory() as unit_of_work:
            account = await unit_of_work.budget_accounts.get_by_project(project_id)
        if account is None:
            raise ResourceNotFound(f"project budget not found: {project_id}")
        return account

    async def list_usage(self, project_id: UUID) -> list[UsageRecord]:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.projects.get(project_id) is None:
                raise ResourceNotFound(f"project not found: {project_id}")
            return await unit_of_work.usage_records.list_by_project(project_id)

    async def reserve(self, claim: TaskClaim) -> BudgetReservation | None:
        selection = claim.model_selection
        if selection is None:
            return None
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.budget_reservations.get_by_key(claim.idempotency_key)
            if existing is not None:
                return existing
            project_id = await self._project_id(unit_of_work, claim.run_id)
            account = await unit_of_work.budget_accounts.get_by_project(project_id, for_update=True)
            if account is None:
                return None
            existing = await unit_of_work.budget_reservations.get_by_key(claim.idempotency_key)
            if existing is not None:
                return existing
            amount = money(selection.estimated_cost_usd)
            account.reserve(amount)
            reservation = BudgetReservation(
                account_id=account.id,
                project_id=project_id,
                run_id=claim.run_id,
                execution_id=claim.execution_id,
                node_key=claim.node_key,
                idempotency_key=claim.idempotency_key,
                reserved_usd=amount,
            )
            await unit_of_work.budget_accounts.save(account)
            await unit_of_work.budget_reservations.add(reservation)
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="budget_reservation",
                    aggregate_id=reservation.id,
                    event_type="budget.reserved",
                    payload={
                        "project_id": str(project_id),
                        "run_id": str(claim.run_id),
                        "amount_usd": str(amount),
                        "idempotency_key": claim.idempotency_key,
                    },
                )
            )
            await unit_of_work.commit()
        return reservation

    async def settle(
        self,
        claim: TaskClaim,
        reservation: BudgetReservation | None,
        usage: TokenUsage | None,
    ) -> UsageRecord | None:
        if reservation is None:
            return None
        if usage is None:
            raise BudgetUsageRequired("model-backed task result must report token usage")
        selection = claim.model_selection
        if selection is None:
            raise BudgetUsageRequired("budget reservation has no model selection")
        return await self._finalize(claim, reservation, usage, UsageKind.ACTUAL)

    async def forfeit(
        self, claim: TaskClaim, reservation: BudgetReservation | None
    ) -> UsageRecord | None:
        if reservation is None:
            return None
        return await self._finalize(
            claim,
            reservation,
            TokenUsage(input_tokens=0, output_tokens=0),
            UsageKind.ESTIMATED_FORFEIT,
        )

    async def _finalize(
        self,
        claim: TaskClaim,
        reservation: BudgetReservation,
        usage: TokenUsage,
        kind: UsageKind,
    ) -> UsageRecord:
        selection = claim.model_selection
        if selection is None:
            raise BudgetUsageRequired("budget reservation has no model selection")
        async with self._unit_of_work_factory() as unit_of_work:
            stored = await unit_of_work.budget_reservations.get_by_key(reservation.idempotency_key)
            if stored is None:
                raise ResourceNotFound(f"budget reservation not found: {reservation.id}")
            account = await unit_of_work.budget_accounts.get_by_project(
                stored.project_id, for_update=True
            )
            if account is None:
                raise ResourceNotFound(f"budget account not found: {stored.account_id}")
            stored = await unit_of_work.budget_reservations.get_by_key(
                reservation.idempotency_key, for_update=True
            )
            if stored is None:
                raise ResourceNotFound(f"budget reservation not found: {reservation.id}")
            existing_usage = await unit_of_work.usage_records.get_by_reservation(stored.id)
            if existing_usage is not None:
                return existing_usage
            if stored.status is not BudgetReservationStatus.RESERVED:
                raise RuntimeError(f"reservation finalized without usage record: {stored.id}")
            if kind is UsageKind.ACTUAL:
                profile = selection.profile
                cost = money(
                    (
                        Decimal(usage.input_tokens) * profile.input_cost_per_million
                        + Decimal(usage.output_tokens) * profile.output_cost_per_million
                    )
                    / _MILLION
                )
                stored.settle(cost)
            else:
                cost = stored.reserved_usd
                stored.forfeit()
            account.settle(stored.reserved_usd, cost)
            record = UsageRecord(
                reservation_id=stored.id,
                account_id=stored.account_id,
                project_id=stored.project_id,
                run_id=stored.run_id,
                execution_id=stored.execution_id,
                node_key=stored.node_key,
                kind=kind,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=cost,
                model_profile_key=selection.profile.key,
                model_profile_version=selection.profile.version,
            )
            await unit_of_work.budget_accounts.save(account)
            await unit_of_work.budget_reservations.save(stored)
            await unit_of_work.usage_records.add(record)
            await unit_of_work.events.append(
                DomainEvent(
                    aggregate_type="budget_reservation",
                    aggregate_id=stored.id,
                    event_type="budget.settled" if kind is UsageKind.ACTUAL else "budget.forfeited",
                    payload={
                        "cost_usd": str(cost),
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "over_budget": account.spent_usd > account.limit_usd,
                    },
                )
            )
            await unit_of_work.commit()
        return record

    @staticmethod
    async def _project_id(unit_of_work: UnitOfWork, run_id: UUID) -> UUID:
        run = await unit_of_work.runs.get(run_id)
        if run is None:
            raise ResourceNotFound(f"run not found: {run_id}")
        request = await unit_of_work.requests.get(run.request_id)
        if request is None:
            raise ResourceNotFound(f"request not found: {run.request_id}")
        return request.project_id
