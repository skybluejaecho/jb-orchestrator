from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jb_orchestrator.application import (
    BudgetService,
    CreateUserRequest,
    ModelCatalogService,
    OrchestrationService,
    PhasePackCatalogService,
    ProjectObservationService,
    RegisterProject,
    SkillCatalogService,
    TaskDispatchService,
    WorkflowService,
)
from jb_orchestrator.domain import DomainEvent, RequestStatus, RunStatus
from jb_orchestrator.infrastructure.database import Base, EventRecord, SqlAlchemyUnitOfWork
from jb_orchestrator.model_routing import (
    ModelProfile,
    ModelRoutingRequest,
    ModelTier,
)
from jb_orchestrator.phase_packs import PhasePackDefinition, PhasePackReference
from jb_orchestrator.skills import SkillDefinition, SkillReference, SkillSourceKind
from jb_orchestrator.worker.models import TaskResult, TokenUsage
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeExecutionStatus,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowStatus,
)


async def test_application_service_round_trip_with_sqlalchemy() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    service = OrchestrationService(lambda: SqlAlchemyUnitOfWork(session_factory))

    project = await service.register_project(
        RegisterProject(
            key="jb-orchestrator",
            name="JB Orchestrator",
            repository_url="https://github.com/example/jb-orchestrator.git",
            default_branch="develop",
        )
    )
    created = await service.create_request(
        CreateUserRequest(project_id=project.id, prompt="Build it")
    )
    stored_request = await service.get_request(created.request.id)
    stored_run = await service.get_run(created.run.id)

    assert stored_request.status is RequestStatus.ACTIVE
    assert stored_run.status is RunStatus.QUEUED
    assert (await service.get_project(project.id)).default_branch == "develop"

    workflow_service = WorkflowService(lambda: SqlAlchemyUnitOfWork(session_factory))
    skill_service = SkillCatalogService(lambda: SqlAlchemyUnitOfWork(session_factory))
    model_service = ModelCatalogService(lambda: SqlAlchemyUnitOfWork(session_factory))
    phase_pack_service = PhasePackCatalogService(lambda: SqlAlchemyUnitOfWork(session_factory))
    skill = await skill_service.register(
        SkillDefinition(
            key="implementation",
            version=1,
            name="Implementation",
            description="Implement an approved task.",
            source_kind=SkillSourceKind.LOCAL,
            source_uri="skills/implementation",
            content_digest="sha256:" + "c" * 64,
        )
    )
    await model_service.register(
        ModelProfile(
            key="integration-balanced",
            version=1,
            name="Integration Balanced",
            provider="test",
            model_id="integration-model",
            tier=ModelTier.BALANCED,
            context_window=32_000,
            input_cost_per_million=Decimal("1"),
            output_cost_per_million=Decimal("4"),
            capabilities=("coding",),
            executor_keys=("integration",),
        )
    )
    phase_pack = await phase_pack_service.register(
        PhasePackDefinition(
            key="implementation",
            version=1,
            name="Implementation",
            description="Implement an approved task.",
            instructions="Apply changes and verify the result.",
            skills=(SkillReference(key=skill.key, version=skill.version),),
        )
    )
    definition = WorkflowDefinition(
        key="delivery",
        version=1,
        entry_node="implement",
        nodes=(
            NodeDefinition(
                key="implement",
                kind=NodeKind.TASK,
                executor_key="integration",
                skills=(SkillReference(key=skill.key, version=skill.version),),
                phase_pack=PhasePackReference(key=phase_pack.key, version=phase_pack.version),
                model_routing=ModelRoutingRequest(required_capabilities=("coding",)),
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="implement", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    await workflow_service.register_definition(definition)
    execution = await workflow_service.start(created.run.id, "delivery")
    dispatch = TaskDispatchService(lambda: SqlAlchemyUnitOfWork(session_factory))
    claim = await dispatch.claim_next("integration-worker", {"integration"})
    assert claim is not None
    assert claim.executor_key == "integration"
    assert claim.phase_pack == phase_pack
    leased_execution = await workflow_service.get(execution.id)
    assert leased_execution.nodes["implement"].worker_id == "integration-worker"
    assert leased_execution.nodes["implement"].lease_token == claim.lease_token
    assert [(item.key, item.version) for item in claim.skills] == [("implementation", 1)]
    assert claim.model_selection is not None
    assert claim.model_selection.profile.model_id == "integration-model"
    budget_service = BudgetService(lambda: SqlAlchemyUnitOfWork(session_factory))
    await budget_service.configure(project.id, Decimal("1.00"))
    reservation = await budget_service.reserve(claim)
    usage_record = await budget_service.settle(
        claim,
        reservation,
        TokenUsage(input_tokens=1_000, output_tokens=500),
    )
    assert usage_record is not None
    assert usage_record.cost_usd == Decimal("0.003000")
    completed_execution = await dispatch.complete(
        claim,
        TaskResult(outcome=NodeOutcome.SUCCESS, output={"commit": "abc123"}),
    )
    stored_execution = await workflow_service.get(execution.id)
    artifacts = await workflow_service.list_artifacts(execution.id)
    assert stored_execution.status is WorkflowStatus.SUCCEEDED
    assert stored_execution.nodes["implement"].status is NodeExecutionStatus.SUCCEEDED
    assert stored_execution.nodes["implement"].output == {"commit": "abc123"}
    assert stored_execution.nodes["implement"].lease_token is None
    assert stored_execution.version == completed_execution.version
    assert len(artifacts) == 1
    assert artifacts[0].producer_node_key == "implement"
    assert artifacts[0].content == {"commit": "abc123"}

    assert (await service.get_run(created.run.id)).status is RunStatus.SUCCEEDED
    assert (await service.get_request(created.request.id)).status is RequestStatus.COMPLETED

    observation_service = ProjectObservationService(lambda: SqlAlchemyUnitOfWork(session_factory))
    observed_requests = await observation_service.list_requests(project.id)
    observed_runs = await observation_service.list_runs(created.request.id)
    observed_workflows = await observation_service.list_workflow_executions(project.id)
    observed_events = await observation_service.list_events(project.id)
    assert [value.id for value in observed_requests] == [created.request.id]
    assert [value.id for value in observed_runs] == [created.run.id]
    assert [value.id for value in observed_workflows] == [execution.id]
    assert "project.registered" in {event.event_type for event in observed_events}
    assert "workflow.started" in {event.event_type for event in observed_events}
    assert "budget.settled" in {event.event_type for event in observed_events}
    assert "skill.registered" not in {event.event_type for event in observed_events}

    async with session_factory() as session:
        event_types = list(await session.scalars(select(EventRecord.event_type)))
    assert sorted(event_types) == sorted(
        [
            "project.registered",
            "request.created",
            "workflow.definition_registered",
            "model.registered",
            "phase_pack.registered",
            "skill.registered",
            "workflow.started",
            "run.status_changed",
            "task.claimed",
            "task.completed",
            "run.status_changed",
            "request.completed",
            "budget.configured",
            "budget.reserved",
            "budget.settled",
        ]
    )

    await engine.dispose()


async def test_event_repository_reads_a_stable_cursor_order() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    occurred_at = datetime(2026, 1, 1, tzinfo=UTC)
    first = DomainEvent(
        id=UUID(int=1),
        aggregate_type="external_execution",
        aggregate_id=uuid4(),
        event_type="external_execution.prepared",
        occurred_at=occurred_at,
    )
    second = DomainEvent(
        id=UUID(int=2),
        aggregate_type="external_execution",
        aggregate_id=first.aggregate_id,
        event_type="external_execution.accepted",
        occurred_at=occurred_at,
    )
    unrelated = DomainEvent(
        id=UUID(int=3),
        aggregate_type="run",
        aggregate_id=uuid4(),
        event_type="run.started",
        occurred_at=occurred_at,
    )

    async with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        await unit_of_work.events.append(first)
        await unit_of_work.events.append(unrelated)
        await unit_of_work.events.append(second)
        await unit_of_work.commit()

    async with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        cursor = await unit_of_work.events.get(first.id)
        events = await unit_of_work.events.list_after(
            aggregate_type="external_execution", after=cursor
        )

    assert cursor is not None
    assert cursor.id == first.id
    assert cursor.sequence == 1
    assert [event.id for event in events] == [second.id]
    assert events[0].sequence == 3
    await engine.dispose()
