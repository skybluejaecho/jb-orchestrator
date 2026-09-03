from jb_orchestrator.application import (
    PhasePackCatalogService,
    TaskDispatchService,
    WorkflowService,
)
from jb_orchestrator.domain import Project, Run, UserRequest
from jb_orchestrator.phase_packs import PhaseInputDefinition, PhasePackDefinition
from jb_orchestrator.worker import TaskResult
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeExecutionStatus,
    NodeInputMapping,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowStatus,
)
from tests.support import MemoryStore, MemoryUnitOfWork


async def test_parallel_workers_join_and_deliver_named_branch_artifacts() -> None:
    store = MemoryStore()
    project = Project(
        key="parallel-project",
        name="Parallel Project",
        repository_url="https://example.com/parallel.git",
        default_branch="develop",
    )
    request = UserRequest(project_id=project.id, prompt="Research and design in parallel.")
    request.activate()
    run = Run(request_id=request.id)
    store.projects[project.id] = project
    store.requests[request.id] = request
    store.runs[run.id] = run

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    synthesis_pack = await PhasePackCatalogService(unit_of_work_factory).register(
        PhasePackDefinition(
            key="synthesis",
            version=1,
            name="Synthesis",
            description="Combine independent branch results.",
            instructions="Synthesize research and design into one recommendation.",
            inputs=(
                PhaseInputDefinition(key="research_result", description="Research evidence"),
                PhaseInputDefinition(key="design_result", description="Design proposal"),
            ),
            output_contract={
                "type": "object",
                "required": ["recommendation"],
                "properties": {"recommendation": {"type": "string"}},
            },
        )
    )
    definition = WorkflowDefinition(
        key="parallel-composition",
        version=1,
        entry_node="fan_out",
        nodes=(
            NodeDefinition(key="fan_out", kind=NodeKind.FORK),
            NodeDefinition(key="research", kind=NodeKind.TASK, executor_key="fake"),
            NodeDefinition(key="design", kind=NodeKind.TASK, executor_key="fake"),
            NodeDefinition(key="fan_in", kind=NodeKind.JOIN),
            NodeDefinition(
                key="synthesize",
                kind=NodeKind.TASK,
                executor_key="fake",
                phase_pack=synthesis_pack.reference,
                input_mappings=(
                    NodeInputMapping(input_key="research_result", source_node="research"),
                    NodeInputMapping(input_key="design_result", source_node="design"),
                ),
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(
            EdgeDefinition(source="fan_out", outcome=NodeOutcome.SUCCESS, target="research"),
            EdgeDefinition(source="fan_out", outcome=NodeOutcome.SUCCESS, target="design"),
            EdgeDefinition(source="research", outcome=NodeOutcome.SUCCESS, target="fan_in"),
            EdgeDefinition(source="design", outcome=NodeOutcome.SUCCESS, target="fan_in"),
            EdgeDefinition(source="fan_in", outcome=NodeOutcome.SUCCESS, target="synthesize"),
            EdgeDefinition(source="synthesize", outcome=NodeOutcome.SUCCESS, target="done"),
        ),
    )
    workflow_service = WorkflowService(unit_of_work_factory)
    dispatch = TaskDispatchService(unit_of_work_factory)
    await workflow_service.register_definition(definition)
    execution = await workflow_service.start(run.id, definition.key)

    first = await dispatch.claim_next("worker-a", {"fake"})
    second = await dispatch.claim_next("worker-b", {"fake"})

    assert first is not None
    assert second is not None
    assert {first.node_key, second.node_key} == {"research", "design"}
    outputs = {
        "research": {"evidence": ["fact-a"]},
        "design": {"proposal": "design-a"},
    }
    await dispatch.complete(
        first,
        TaskResult(outcome=NodeOutcome.SUCCESS, output=outputs[first.node_key]),
    )
    partially_complete = await workflow_service.get(execution.id)
    assert partially_complete.nodes["fan_in"].status is NodeExecutionStatus.PENDING

    await dispatch.complete(
        second,
        TaskResult(outcome=NodeOutcome.SUCCESS, output=outputs[second.node_key]),
    )
    synthesis = await dispatch.claim_next("worker-c", {"fake"})

    assert synthesis is not None
    assert synthesis.node_key == "synthesize"
    assert synthesis.context is not None
    named_inputs = {value.name: value.artifact.content for value in synthesis.context.named_inputs}
    assert named_inputs == {
        "design_result": outputs["design"],
        "research_result": outputs["research"],
    }
    completed = await dispatch.complete(
        synthesis,
        TaskResult(
            outcome=NodeOutcome.SUCCESS,
            output={"recommendation": "combine both results"},
        ),
    )
    assert completed.status is WorkflowStatus.SUCCEEDED
