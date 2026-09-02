from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from jb_orchestrator.application import BudgetService, OrchestrationService
from jb_orchestrator.budgets import (
    BudgetLimitExceeded,
    BudgetReservationStatus,
    UsageKind,
)
from jb_orchestrator.domain import Project, Run, UserRequest
from jb_orchestrator.model_routing import (
    DeterministicModelRouter,
    ModelProfile,
    ModelRoutingRequest,
    ModelTier,
)
from jb_orchestrator.worker import TaskClaim, TokenUsage
from tests.support import MemoryStore, MemoryUnitOfWork


def model_selection():
    profile = ModelProfile(
        key="codex-balanced",
        version=1,
        name="Codex Balanced",
        provider="openai",
        model_id="gpt-codex",
        tier=ModelTier.BALANCED,
        context_window=128_000,
        input_cost_per_million=Decimal("1"),
        output_cost_per_million=Decimal("4"),
        executor_keys=("codex",),
    )
    return DeterministicModelRouter().route(
        ModelRoutingRequest(estimated_input_tokens=100_000, max_output_tokens=10_000),
        (profile,),
        executor_key="codex",
    )


def budget_context() -> tuple[MemoryStore, Project, TaskClaim]:
    store = MemoryStore()
    project = Project(
        key="budget-test",
        name="Budget Test",
        repository_url="https://example.com/repository.git",
    )
    request = UserRequest(project_id=project.id, prompt="Implement it")
    run = Run(request_id=request.id)
    store.projects[project.id] = project
    store.requests[request.id] = request
    store.runs[run.id] = run
    claim = TaskClaim(
        execution_id=uuid4(),
        run_id=run.id,
        node_key="implement",
        executor_key="codex",
        worker_id="worker-a",
        lease_token=uuid4(),
        idempotency_key=f"{run.id}:implement:1",
        visit_count=1,
        attempt_count=1,
        timeout_seconds=60,
        workflow_key="delivery",
        workflow_version=1,
        instructions="Implement it",
        configuration={},
        skills=(),
        model_selection=model_selection(),
    )
    return store, project, claim


async def test_reservation_and_settlement_are_idempotent() -> None:
    store, project, claim = budget_context()
    service = BudgetService(lambda: MemoryUnitOfWork(store))
    await service.configure(project.id, Decimal("1.00"))

    first = await service.reserve(claim)
    second = await service.reserve(claim)

    assert first is not None
    assert second is first
    assert store.budget_accounts[project.id].reserved_usd == Decimal("0.140000")

    usage = TokenUsage(input_tokens=50_000, output_tokens=5_000)
    first_record = await service.settle(claim, first, usage)
    second_record = await service.settle(claim, first, usage)

    assert first_record is not None
    assert second_record == first_record
    assert first.status is BudgetReservationStatus.SETTLED
    assert first_record.kind is UsageKind.ACTUAL
    assert first_record.cost_usd == Decimal("0.070000")
    assert store.budget_accounts[project.id].reserved_usd == Decimal("0.000000")
    assert store.budget_accounts[project.id].spent_usd == Decimal("0.070000")
    assert len(store.usage_records) == 1


async def test_reservation_fails_closed_when_available_budget_is_too_low() -> None:
    store, project, claim = budget_context()
    service = BudgetService(lambda: MemoryUnitOfWork(store))
    await service.configure(project.id, Decimal("0.10"))

    with pytest.raises(BudgetLimitExceeded, match=r"only 0\.100000"):
        await service.reserve(claim)

    assert not store.budget_reservations


async def test_actual_overrun_is_recorded_and_blocks_future_reservations() -> None:
    store, project, claim = budget_context()
    service = BudgetService(lambda: MemoryUnitOfWork(store))
    await service.configure(project.id, Decimal("0.14"))
    reservation = await service.reserve(claim)
    assert reservation is not None

    await service.settle(
        claim,
        reservation,
        TokenUsage(input_tokens=200_000, output_tokens=20_000),
    )

    account = store.budget_accounts[project.id]
    assert account.spent_usd == Decimal("0.280000")
    assert account.available_usd == Decimal("-0.140000")
    next_claim = replace(
        claim,
        idempotency_key=f"{claim.run_id}:review:1",
        node_key="review",
    )
    with pytest.raises(BudgetLimitExceeded):
        await service.reserve(next_claim)


async def test_final_unknown_usage_forfeits_reserved_amount() -> None:
    store, project, claim = budget_context()
    service = BudgetService(lambda: MemoryUnitOfWork(store))
    await service.configure(project.id, Decimal("1.00"))
    reservation = await service.reserve(claim)

    record = await service.forfeit(claim, reservation)

    assert reservation is not None
    assert reservation.status is BudgetReservationStatus.FORFEITED
    assert record is not None
    assert record.kind is UsageKind.ESTIMATED_FORFEIT
    assert record.cost_usd == Decimal("0.140000")


async def test_cancelling_run_releases_active_reservations() -> None:
    store, project, claim = budget_context()
    service = BudgetService(lambda: MemoryUnitOfWork(store))
    await service.configure(project.id, Decimal("1.00"))
    reservation = await service.reserve(claim)
    assert reservation is not None

    await OrchestrationService(lambda: MemoryUnitOfWork(store)).cancel_run(claim.run_id)

    assert reservation.status is BudgetReservationStatus.RELEASED
    assert store.budget_accounts[project.id].reserved_usd == Decimal("0.000000")
    assert store.budget_accounts[project.id].available_usd == Decimal("1.000000")
    assert store.events[-2].event_type == "budget.released"
    assert store.events[-1].event_type == "run.cancelled"
