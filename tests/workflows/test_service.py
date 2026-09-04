from decimal import Decimal

import pytest

from jb_orchestrator.application import (
    ModelCatalogService,
    PhasePackCatalogService,
    SkillCatalogService,
    TaskDispatchService,
    WorkflowService,
)
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.domain import Project, Run, UserRequest
from jb_orchestrator.model_routing import (
    ModelProfile,
    ModelRoutingRequest,
    ModelTier,
    RequirementLevel,
)
from jb_orchestrator.phase_packs import (
    PhaseInputDefinition,
    PhasePackDefinition,
    PhasePackReference,
)
from jb_orchestrator.skills import SkillDefinition, SkillReference, SkillSourceKind
from jb_orchestrator.worker import TaskResult
from jb_orchestrator.workflows import (
    ArtifactCondition,
    EdgeDefinition,
    NodeDefinition,
    NodeExecutionStatus,
    NodeInputMapping,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowDefinitionError,
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


def store_run_context(store: MemoryStore) -> Run:
    project = Project(
        key="test-project",
        name="Test Project",
        repository_url="https://example.com/project.git",
        default_branch="develop",
    )
    request = UserRequest(
        project_id=project.id,
        prompt="Implement and verify the requested change.",
        title="Test request",
    )
    request.activate()
    run = Run(request_id=request.id)
    store.projects[project.id] = project
    store.requests[request.id] = request
    store.runs[run.id] = run
    return run


async def test_service_persists_versioned_snapshot_and_events() -> None:
    store = MemoryStore()
    run = store_run_context(store)
    service = WorkflowService(lambda: MemoryUnitOfWork(store))
    await service.register_definition(simple_definition(version=1))
    latest = await service.register_definition(simple_definition(version=2))

    execution = await service.start(run.id, "simple")
    assert execution.snapshot.definition_id == latest.id
    assert execution.snapshot.definition_version == 2
    assert execution.snapshot.request_context is not None
    assert execution.snapshot.request_context.prompt == "Implement and verify the requested change."
    assert execution.snapshot.request_context.default_branch == "develop"
    assert execution.nodes["work"].status is NodeExecutionStatus.READY

    await service.begin_task(execution.id, "work")
    completed = await service.complete_task(
        execution.id, "work", NodeOutcome.SUCCESS, {"artifact": "result.md"}
    )

    assert completed.status is WorkflowStatus.SUCCEEDED
    assert completed.nodes["work"].output == {"artifact": "result.md"}
    assert len(store.artifacts) == 1
    assert store.artifacts[0].content == {"artifact": "result.md"}
    assert [event.event_type for event in store.events] == [
        "workflow.definition_registered",
        "workflow.definition_registered",
        "workflow.started",
        "run.status_changed",
        "workflow.node_started",
        "workflow.node_completed",
        "run.status_changed",
        "request.completed",
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
    run = store_run_context(store)
    service = WorkflowService(lambda: MemoryUnitOfWork(store))
    await service.register_definition(simple_definition())
    await service.start(run.id, "simple")

    with pytest.raises(ResourceConflict, match="already exists"):
        await service.start(run.id, "simple")


async def test_workflow_snapshot_resolves_exact_skill_versions() -> None:
    store = MemoryStore()
    run = store_run_context(store)

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
    run = store_run_context(store)

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


async def test_next_task_claim_receives_request_context_and_direct_artifact() -> None:
    store = MemoryStore()
    run = store_run_context(store)
    definition = WorkflowDefinition(
        key="context-flow",
        version=1,
        entry_node="plan",
        nodes=(
            NodeDefinition(key="plan", kind=NodeKind.TASK, executor_key="fake"),
            NodeDefinition(key="implement", kind=NodeKind.TASK, executor_key="fake"),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(
            EdgeDefinition(source="plan", outcome=NodeOutcome.SUCCESS, target="implement"),
            EdgeDefinition(source="implement", outcome=NodeOutcome.SUCCESS, target="done"),
        ),
    )

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    workflow_service = WorkflowService(unit_of_work_factory)
    dispatch = TaskDispatchService(unit_of_work_factory)
    await workflow_service.register_definition(definition)
    execution = await workflow_service.start(run.id, definition.key)

    planning = await dispatch.claim_next("worker-a", {"fake"})
    assert planning is not None
    await dispatch.complete(
        planning,
        TaskResult(
            outcome=NodeOutcome.SUCCESS,
            output={"requirements": ["preserve context", "verify output"]},
        ),
    )
    implementation = await dispatch.claim_next("worker-b", {"fake"})

    assert implementation is not None
    assert implementation.node_key == "implement"
    assert implementation.context is not None
    assert implementation.context.request.request_id == run.request_id
    assert implementation.context.request.prompt == "Implement and verify the requested change."
    assert len(implementation.context.upstream_artifacts) == 1
    artifact = implementation.context.upstream_artifacts[0]
    assert artifact.execution_id == execution.id
    assert artifact.producer_node_key == "plan"
    assert artifact.visit_count == 1
    assert artifact.content == {"requirements": ["preserve context", "verify output"]}


async def test_phase_pack_pins_contract_and_maps_named_artifact_input() -> None:
    store = MemoryStore()
    run = store_run_context(store)

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    phase_pack = await PhasePackCatalogService(unit_of_work_factory).register(
        PhasePackDefinition(
            key="implementation",
            version=1,
            name="Implementation",
            description="Implement an approved plan.",
            instructions="Change the repository and verify the result.",
            inputs=(
                PhaseInputDefinition(
                    key="approved_plan", description="The approved implementation plan."
                ),
            ),
            output_contract={"required": ["summary", "tests"]},
        )
    )
    definition = WorkflowDefinition(
        key="phase-composition",
        version=1,
        entry_node="plan",
        nodes=(
            NodeDefinition(key="plan", kind=NodeKind.TASK, executor_key="fake"),
            NodeDefinition(
                key="implement",
                kind=NodeKind.TASK,
                executor_key="fake",
                phase_pack=PhasePackReference(key=phase_pack.key, version=phase_pack.version),
                input_mappings=(NodeInputMapping(input_key="approved_plan", source_node="plan"),),
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(
            EdgeDefinition(source="plan", outcome=NodeOutcome.SUCCESS, target="implement"),
            EdgeDefinition(source="implement", outcome=NodeOutcome.SUCCESS, target="done"),
        ),
    )
    workflow_service = WorkflowService(unit_of_work_factory)
    dispatch = TaskDispatchService(unit_of_work_factory)
    await workflow_service.register_definition(definition)
    execution = await workflow_service.start(run.id, definition.key)

    planning = await dispatch.claim_next("planner", {"fake"})
    assert planning is not None
    await dispatch.complete(
        planning,
        TaskResult(outcome=NodeOutcome.SUCCESS, output={"steps": ["edit", "test"]}),
    )
    implementation = await dispatch.claim_next("implementer", {"fake"})

    assert implementation is not None
    assert implementation.phase_pack == phase_pack
    assert execution.snapshot.phase_packs == (phase_pack,)
    assert implementation.context is not None
    assert len(implementation.context.named_inputs) == 1
    resolved_input = implementation.context.named_inputs[0]
    assert resolved_input.name == "approved_plan"
    assert resolved_input.artifact.producer_node_key == "plan"
    assert resolved_input.artifact.content == {"steps": ["edit", "test"]}


async def test_workflow_rejects_missing_required_phase_input_mapping() -> None:
    store = MemoryStore()

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    phase_pack = await PhasePackCatalogService(unit_of_work_factory).register(
        PhasePackDefinition(
            key="verification",
            version=1,
            name="Verification",
            description="Verify an implementation.",
            instructions="Check the implementation evidence.",
            inputs=(PhaseInputDefinition(key="implementation", description="Implemented change"),),
        )
    )
    definition = WorkflowDefinition(
        key="invalid-phase-inputs",
        version=1,
        entry_node="verify",
        nodes=(
            NodeDefinition(
                key="verify",
                kind=NodeKind.TASK,
                phase_pack=phase_pack.reference,
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="verify", outcome=NodeOutcome.SUCCESS, target="done"),),
    )

    with pytest.raises(WorkflowDefinitionError, match="missing required phase inputs"):
        await WorkflowService(unit_of_work_factory).register_definition(definition)


async def test_invalid_phase_output_routes_to_repair_with_structured_artifact() -> None:
    store = MemoryStore()
    run = store_run_context(store)

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    phase_pack = await PhasePackCatalogService(unit_of_work_factory).register(
        PhasePackDefinition(
            key="verification",
            version=1,
            name="Verification",
            description="Verify an implementation.",
            instructions="Return a verdict and findings.",
            output_contract={
                "type": "object",
                "required": ["verdict", "findings"],
                "properties": {
                    "verdict": {"enum": ["approved", "rejected"]},
                    "findings": {"type": "array"},
                },
            },
        )
    )
    definition = WorkflowDefinition(
        key="contract-repair",
        version=1,
        entry_node="verify",
        nodes=(
            NodeDefinition(
                key="verify",
                kind=NodeKind.TASK,
                executor_key="fake",
                max_visits=2,
                phase_pack=phase_pack.reference,
            ),
            NodeDefinition(key="repair", kind=NodeKind.TASK, executor_key="fake"),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(
            EdgeDefinition(source="verify", outcome=NodeOutcome.SUCCESS, target="done"),
            EdgeDefinition(source="verify", outcome=NodeOutcome.FAILURE, target="repair"),
            EdgeDefinition(source="repair", outcome=NodeOutcome.SUCCESS, target="verify"),
        ),
    )
    workflow_service = WorkflowService(unit_of_work_factory)
    dispatch = TaskDispatchService(unit_of_work_factory)
    await workflow_service.register_definition(definition)
    await workflow_service.start(run.id, definition.key)

    verification = await dispatch.claim_next("verifier", {"fake"})
    assert verification is not None
    routed = await dispatch.complete(
        verification,
        TaskResult(outcome=NodeOutcome.SUCCESS, output={"verdict": "unknown"}),
    )

    assert routed.status is WorkflowStatus.RUNNING
    assert routed.nodes["verify"].outcome is NodeOutcome.FAILURE
    assert routed.nodes["repair"].status is NodeExecutionStatus.READY
    artifact = store.artifacts[-1]
    assert artifact.outcome is NodeOutcome.FAILURE
    assert artifact.content["rejected_output"] == {"verdict": "unknown"}
    errors = artifact.content["contract_violation"]["errors"]
    assert [(value["path"], value["keyword"]) for value in errors] == [
        ("$", "required"),
        ("$.verdict", "enum"),
    ]
    assert store.events[-1].payload["output_contract_rejected"] is True

    repair = await dispatch.claim_next("repairer", {"fake"})
    assert repair is not None
    assert repair.node_key == "repair"
    assert repair.context is not None
    assert repair.context.upstream_artifacts[0] == artifact


async def test_valid_phase_artifact_routes_by_declared_condition() -> None:
    store = MemoryStore()
    run = store_run_context(store)

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    phase_pack = await PhasePackCatalogService(unit_of_work_factory).register(
        PhasePackDefinition(
            key="semantic-verification",
            version=1,
            name="Semantic Verification",
            description="Return a machine-routable verdict.",
            instructions="Verify the implementation.",
            output_contract={
                "type": "object",
                "required": ["verdict"],
                "properties": {
                    "verdict": {"enum": ["approve", "changes_requested"]},
                },
                "additionalProperties": False,
            },
        )
    )
    definition = WorkflowDefinition(
        key="semantic-repair",
        version=1,
        entry_node="verify",
        nodes=(
            NodeDefinition(
                key="verify",
                kind=NodeKind.TASK,
                executor_key="fake",
                phase_pack=phase_pack.reference,
            ),
            NodeDefinition(key="repair", kind=NodeKind.TASK, executor_key="fake"),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(
            EdgeDefinition(
                source="verify",
                outcome=NodeOutcome.SUCCESS,
                target="done",
                condition=ArtifactCondition(path="/verdict", equals="approve"),
            ),
            EdgeDefinition(
                source="verify",
                outcome=NodeOutcome.SUCCESS,
                target="repair",
                condition=ArtifactCondition(path="/verdict", equals="changes_requested"),
            ),
            EdgeDefinition(source="repair", outcome=NodeOutcome.SUCCESS, target="done"),
        ),
    )
    workflow_service = WorkflowService(unit_of_work_factory)
    dispatch = TaskDispatchService(unit_of_work_factory)
    await workflow_service.register_definition(definition)
    await workflow_service.start(run.id, definition.key)
    verification = await dispatch.claim_next("verifier", {"fake"})
    assert verification is not None

    routed = await dispatch.complete(
        verification,
        TaskResult(
            outcome=NodeOutcome.SUCCESS,
            output={"verdict": "changes_requested"},
        ),
    )

    assert routed.status is WorkflowStatus.RUNNING
    assert routed.nodes["repair"].status is NodeExecutionStatus.READY
    assert store.artifacts[-1].outcome is NodeOutcome.SUCCESS
    assert store.artifacts[-1].content == {"verdict": "changes_requested"}
    assert store.events[-1].payload["output_contract_rejected"] is False


async def test_direct_workflow_completion_enforces_phase_output_contract() -> None:
    store = MemoryStore()
    run = store_run_context(store)

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    phase_pack = await PhasePackCatalogService(unit_of_work_factory).register(
        PhasePackDefinition(
            key="summary",
            version=1,
            name="Summary",
            description="Produce a structured summary.",
            instructions="Return the requested summary.",
            output_contract={
                "type": "object",
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
            },
        )
    )
    definition = WorkflowDefinition(
        key="direct-contract",
        version=1,
        entry_node="summarize",
        nodes=(
            NodeDefinition(
                key="summarize",
                kind=NodeKind.TASK,
                phase_pack=phase_pack.reference,
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="summarize", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    service = WorkflowService(unit_of_work_factory)
    await service.register_definition(definition)
    execution = await service.start(run.id, definition.key)
    await service.begin_task(execution.id, "summarize")

    completed = await service.complete_task(
        execution.id,
        "summarize",
        NodeOutcome.SUCCESS,
        {"unexpected": True},
    )

    assert completed.status is WorkflowStatus.FAILED
    assert completed.nodes["summarize"].outcome is NodeOutcome.FAILURE
    assert store.artifacts[-1].content["contract_violation"]["reason"] == (
        "output_contract_violation"
    )
