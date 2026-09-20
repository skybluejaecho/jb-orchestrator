from decimal import Decimal
from uuid import uuid4

from jb_orchestrator.model_routing import (
    DeterministicModelRouter,
    ModelProfile,
    ModelRoutingRequest,
    ModelTier,
    NodeModelSelection,
)
from jb_orchestrator.phase_packs import (
    PhaseInputDefinition,
    PhasePackDefinition,
    PhasePackReference,
)
from jb_orchestrator.workflows import (
    ArtifactCondition,
    EdgeDefinition,
    NodeDefinition,
    NodeInputMapping,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowRequestContext,
    WorkflowSnapshot,
    WorkflowStatus,
)
from jb_orchestrator.workflows.serialization import (
    definition_from_dict,
    definition_to_dict,
    snapshot_from_dict,
    snapshot_to_dict,
)


def test_definition_and_snapshot_json_round_trip() -> None:
    phase_pack = PhasePackDefinition(
        key="implementation",
        version=1,
        name="Implementation",
        description="Implement a plan.",
        instructions="Apply the approved plan.",
        inputs=(PhaseInputDefinition(key="plan", description="Approved plan"),),
        output_contract={"required": ["summary"]},
    )
    definition = WorkflowDefinition(
        key="serialized",
        version=3,
        entry_node="prepare",
        nodes=(
            NodeDefinition(
                key="task",
                kind=NodeKind.TASK,
                max_attempts=2,
                executor_key="codex",
                instructions="Implement the approved task.",
                configuration={"reasoning_effort": "medium"},
                phase_pack=PhasePackReference(key="implementation", version=1),
                input_mappings=(NodeInputMapping(input_key="plan", source_node="prepare"),),
                model_routing=ModelRoutingRequest(
                    required_capabilities=("coding",),
                    max_cost_usd=Decimal("1.00"),
                ),
            ),
            NodeDefinition(key="prepare", kind=NodeKind.TASK),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(
            EdgeDefinition(
                source="task",
                outcome=NodeOutcome.SUCCESS,
                target="done",
                condition=ArtifactCondition(path="/summary", equals="complete"),
            ),
            EdgeDefinition(source="prepare", outcome=NodeOutcome.SUCCESS, target="task"),
        ),
    )
    profile = ModelProfile(
        key="codex-balanced",
        version=2,
        name="Codex Balanced",
        provider="openai",
        model_id="gpt-codex",
        tier=ModelTier.BALANCED,
        context_window=128_000,
        input_cost_per_million=Decimal("1"),
        output_cost_per_million=Decimal("4"),
        capabilities=("coding",),
        executor_keys=("codex",),
    )
    request = definition.node("task").model_routing
    assert request is not None
    selection = DeterministicModelRouter().route(request, (profile,), executor_key="codex")
    snapshot = WorkflowSnapshot.from_definition(
        definition,
        run_id=uuid4(),
        request_context=WorkflowRequestContext(
            request_id=uuid4(),
            project_id=uuid4(),
            project_key="serialized-project",
            project_name="Serialized Project",
            repository_url="https://example.com/project.git",
            default_branch="develop",
            prompt="Implement the serialized workflow.",
            title="Serialized request",
        ),
        phase_packs=(phase_pack,),
        model_selections=(NodeModelSelection(node_key="task", selection=selection),),
    )

    restored_definition = definition_from_dict(definition_to_dict(definition))
    restored_snapshot = snapshot_from_dict(snapshot_to_dict(snapshot))

    assert restored_definition == definition
    assert restored_snapshot == snapshot
