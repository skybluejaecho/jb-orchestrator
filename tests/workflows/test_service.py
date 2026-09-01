from uuid import uuid4

import pytest

from jb_orchestrator.application import SkillCatalogService, WorkflowService
from jb_orchestrator.application.exceptions import ResourceConflict
from jb_orchestrator.domain import Run
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
