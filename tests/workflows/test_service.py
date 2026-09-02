from decimal import Decimal
from uuid import uuid4

import pytest

from jb_orchestrator.application import (
    ModelCatalogService,
    SkillCatalogService,
    TaskDispatchService,
    WorkflowService,
)
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.domain import Run
from jb_orchestrator.model_routing import (
    ModelProfile,
    ModelRoutingRequest,
    ModelTier,
    RequirementLevel,
)
from jb_orchestrator.skills import SkillDefinition, SkillReference, SkillSourceKind
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeExecutionStatus,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowStatus,
)
from tests.support import MemoryStore, MemoryUnitOfWork


def simple_definition(*, version: int = 1) -> WorkflowDefinition:
    return WorkflowDefinition(
        key="simple",
        version=version,
        entry_node="work",
        nodes=(
            NodeDefinition(key="work", kind=NodeKind.TASK),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="work", outcome=NodeOutcome.SUCCESS, target="done"),),
    )


async def test_service_persists_versioned_snapshot_and_events() -> None:
    store = MemoryStore()
    run = Run(request_id=uuid4())
    store.runs[run.id] = run
    service = WorkflowService(lambda: MemoryUnitOfWork(store))
    await service.register_definition(simple_definition(version=1))
    latest = await service.register_definition(simple_definition(version=2))

    execution = await service.start(run.id, "simple")
    assert execution.snapshot.definition_id == latest.id
    assert execution.snapshot.definition_version == 2
    assert execution.nodes["work"].status is NodeExecutionStatus.READY

    await service.begin_task(execution.id, "work")
    completed = await service.complete_task(
        execution.id, "work", NodeOutcome.SUCCESS, {"artifact": "result.md"}
    )

    assert completed.status is WorkflowStatus.SUCCEEDED
    assert completed.nodes["work"].output == {"artifact": "result.md"}
    assert [event.event_type for event in store.events] == [
        "workflow.definition_registered",
        "workflow.definition_registered",
        "workflow.started",
        "workflow.node_started",
        "workflow.node_completed",
    ]


async def test_service_lists_latest_definitions_and_gets_exact_version() -> None:
    store = MemoryStore()
    service = WorkflowService(lambda: MemoryUnitOfWork(store))
    await service.register_definition(simple_definition(version=1))
    latest = await service.register_definition(simple_definition(version=2))
    other = WorkflowDefinition(
        key="other",
        version=1,
        entry_node="done",
        nodes=(
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(),
    )
    await service.register_definition(other)

    definitions = await service.list_latest_definitions()
    exact = await service.get_definition("simple", 1)

    assert [(definition.key, definition.version) for definition in definitions] == [
        ("other", 1),
        ("simple", 2),
    ]
    assert exact.version == 1
    assert (await service.get_definition("simple")).id == latest.id

    with pytest.raises(ResourceNotFound, match="missing@1"):
        await service.get_definition("missing", 1)


async def test_service_allows_only_one_execution_per_run() -> None:
    store = MemoryStore()
    run = Run(request_id=uuid4())
    store.runs[run.id] = run
    service = WorkflowService(lambda: MemoryUnitOfWork(store))
    await service.register_definition(simple_definition())
    await service.start(run.id, "simple")

    with pytest.raises(ResourceConflict, match="already exists"):
        await service.start(run.id, "simple")


async def test_workflow_snapshot_resolves_exact_skill_versions() -> None:
    store = MemoryStore()
    run = Run(request_id=uuid4())
    store.runs[run.id] = run

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    skill_service = SkillCatalogService(unit_of_work_factory)
    workflow_service = WorkflowService(unit_of_work_factory)
    digest = "sha256:" + "b" * 64
    for version in (1, 2):
        await skill_service.register(
            SkillDefinition(
                key="review",
                version=version,
                name="Review",
                description="Review code",
                source_kind=SkillSourceKind.GIT,
                source_uri="https://example.com/review.git",
                content_digest=digest,
                source_revision="abc123",
            )
        )
    definition = WorkflowDefinition(
        key="skilled",
        version=1,
        entry_node="work",
        nodes=(
            NodeDefinition(
                key="work",
                kind=NodeKind.TASK,
                skills=(SkillReference(key="review", version=1),),
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="work", outcome=NodeOutcome.SUCCESS, target="done"),),
    )

    await workflow_service.register_definition(definition)
    execution = await workflow_service.start(run.id, "skilled")

    assert [(skill.key, skill.version) for skill in execution.snapshot.skills] == [("review", 1)]


async def test_workflow_snapshot_pins_model_routing_decision_in_task_claim() -> None:
    store = MemoryStore()
    run = Run(request_id=uuid4())
    store.runs[run.id] = run

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    await ModelCatalogService(unit_of_work_factory).register(
        ModelProfile(
            key="codex-advanced",
            version=1,
            name="Codex Advanced",
            provider="openai",
            model_id="gpt-codex-advanced",
            tier=ModelTier.ADVANCED,
            context_window=128_000,
            input_cost_per_million=Decimal("2"),
            output_cost_per_million=Decimal("8"),
            capabilities=("coding",),
            executor_keys=("codex",),
        )
    )
    definition = WorkflowDefinition(
        key="routed",
        version=1,
        entry_node="work",
        nodes=(
            NodeDefinition(
                key="work",
                kind=NodeKind.TASK,
                executor_key="codex",
                model_routing=ModelRoutingRequest(
                    complexity=RequirementLevel.HIGH,
                    risk=RequirementLevel.HIGH,
                    required_capabilities=("coding",),
                    estimated_input_tokens=10_000,
                    max_output_tokens=2_000,
                ),
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="work", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    service = WorkflowService(unit_of_work_factory)
    await service.register_definition(definition)

    execution = await service.start(run.id, "routed")
    claim = await TaskDispatchService(unit_of_work_factory).claim_next("worker-a", {"codex"})

    assert execution.snapshot.model_selections[0].selection.profile.version == 1
    assert claim is not None
    assert claim.model_selection is not None
    assert claim.model_selection.profile.model_id == "gpt-codex-advanced"
    assert claim.model_selection.policy_version == 1
    assert claim.model_selection.estimated_cost_usd == Decimal("0.036")
