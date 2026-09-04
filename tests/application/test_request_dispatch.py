import pytest

from jb_orchestrator.application import (
    DispatchProjectRequest,
    NodeSkillAddon,
    RequestDispatchService,
    WorkflowService,
)
from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.domain import Project, RequestOrigin
from jb_orchestrator.phase_packs import PhasePackDefinition, PhasePackReference
from jb_orchestrator.skills import SkillDefinition, SkillReference, SkillSourceKind
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    NodeKind,
    NodeOutcome,
    WorkflowDefinition,
    WorkflowStatus,
)
from tests.support import MemoryStore, MemoryUnitOfWork


def definition(version: int) -> WorkflowDefinition:
    return WorkflowDefinition(
        key="delivery",
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


def dispatch_command(
    project: Project,
    prompt: str,
    key: str,
    title: str | None = None,
    *,
    ingress_key: str = "test",
    definition_key: str | None = None,
    definition_version: int | None = None,
    skill_addons: tuple[NodeSkillAddon, ...] = (),
) -> DispatchProjectRequest:
    return DispatchProjectRequest(
        project_id=project.id,
        prompt=prompt,
        title=title,
        idempotency_key=key,
        origin=RequestOrigin(ingress_key=ingress_key, external_request_id=key),
        definition_key=definition_key,
        definition_version=definition_version,
        skill_addons=skill_addons,
    )


async def test_binding_pins_exact_version_and_dispatches_all_state() -> None:
    store = MemoryStore()
    project = Project(
        key="dispatch-project",
        name="Dispatch Project",
        repository_url="https://example.com/dispatch.git",
        default_branch="develop",
    )
    store.projects[project.id] = project

    def unit_of_work_factory() -> MemoryUnitOfWork:
        return MemoryUnitOfWork(store)

    workflows = WorkflowService(unit_of_work_factory)
    service = RequestDispatchService(unit_of_work_factory, workflows)
    first = await workflows.register_definition(definition(1))
    await workflows.register_definition(definition(2))

    binding = await service.configure_binding(project.id, "delivery", 1)
    dispatched = await service.dispatch(
        dispatch_command(
            project,
            "Ship the requested change",
            "delivery-1",
            "Delivery",
        )
    )

    assert binding.definition_id == first.id
    assert dispatched.request.id in store.requests
    assert dispatched.run.id in store.runs
    assert dispatched.workflow.id in store.workflow_executions
    assert dispatched.workflow.snapshot.definition_version == 1
    assert dispatched.workflow.snapshot.request_context is not None
    assert dispatched.workflow.snapshot.request_context.prompt == "Ship the requested change"
    assert dispatched.request.origin == RequestOrigin(
        ingress_key="test", external_request_id="delivery-1"
    )
    assert [event.event_type for event in store.events[-4:]] == [
        "project.workflow_bound",
        "request.created",
        "workflow.started",
        "run.status_changed",
    ]
    assert store.events[-2].payload["selection_source"] == "project_binding"
    assert store.events[-3].payload["origin"]["ingress_key"] == "test"


async def test_binding_update_affects_only_future_dispatches() -> None:
    store = MemoryStore()
    project = Project(
        key="versioned-project",
        name="Versioned Project",
        repository_url="https://example.com/versioned.git",
    )
    store.projects[project.id] = project
    factory = lambda: MemoryUnitOfWork(store)  # noqa: E731
    workflows = WorkflowService(factory)
    service = RequestDispatchService(factory, workflows)
    await workflows.register_definition(definition(1))
    await workflows.register_definition(definition(2))

    await service.configure_binding(project.id, "delivery", 1)
    first = await service.dispatch(dispatch_command(project, "First", "first"))
    await service.configure_binding(project.id, "delivery", 2)
    second = await service.dispatch(dispatch_command(project, "Second", "second"))

    assert first.workflow.snapshot.definition_version == 1
    assert second.workflow.snapshot.definition_version == 2


async def test_request_override_selects_exact_workflow_without_project_binding() -> None:
    store = MemoryStore()
    project = Project(
        key="override-project",
        name="Override Project",
        repository_url="https://example.com/override.git",
    )
    store.projects[project.id] = project
    factory = lambda: MemoryUnitOfWork(store)  # noqa: E731
    workflows = WorkflowService(factory)
    service = RequestDispatchService(factory, workflows)
    selected = await workflows.register_definition(definition(2))

    dispatched = await service.dispatch(
        dispatch_command(
            project,
            "Plan only",
            "override-1",
            definition_key=selected.key,
            definition_version=selected.version,
        )
    )

    assert dispatched.workflow.snapshot.definition_id == selected.id
    assert dispatched.workflow.snapshot.definition_version == 2
    assert store.events[-2].payload["selection_source"] == "request_override"
    assert store.events[-3].payload["workflow_selection"] == {
        "source": "request_override",
        "definition_key": "delivery",
        "definition_version": 2,
    }


async def test_workflow_options_include_default_and_latest_definitions() -> None:
    store = MemoryStore()
    project = Project(
        key="options-project",
        name="Options Project",
        repository_url="https://example.com/options.git",
    )
    store.projects[project.id] = project
    factory = lambda: MemoryUnitOfWork(store)  # noqa: E731
    workflows = WorkflowService(factory)
    service = RequestDispatchService(factory, workflows)
    await workflows.register_definition(definition(1))
    latest = await workflows.register_definition(definition(2))
    await service.configure_binding(project.id, latest.key, latest.version)

    options = await service.list_workflow_options(project.id)

    assert options.default is not None
    assert options.default.definition_id == latest.id
    assert options.default_workflow is not None
    assert options.default_workflow.definition == latest
    assert [(value.key, value.version) for value in options.workflows] == [("delivery", 2)]


async def test_workflow_options_resolve_phase_packs_and_effective_skills() -> None:
    store = MemoryStore()
    project = Project(
        key="composition-project",
        name="Composition Project",
        repository_url="https://example.com/composition.git",
    )
    skill = SkillDefinition(
        key="review",
        version=1,
        name="Review",
        description="Review the proposed change",
        source_kind=SkillSourceKind.LOCAL,
        source_uri="review",
        content_digest=f"sha256:{'a' * 64}",
    )
    phase_pack = PhasePackDefinition(
        key="verification",
        version=1,
        name="Verification",
        description="Verify implementation output",
        instructions="Inspect the implementation.",
        skills=(skill.reference,),
    )
    workflow = WorkflowDefinition(
        key="composed-delivery",
        version=1,
        entry_node="verify",
        nodes=(
            NodeDefinition(
                key="verify",
                kind=NodeKind.TASK,
                phase_pack=PhasePackReference(key="verification", version=1),
                skills=(SkillReference(key="review", version=1),),
            ),
            NodeDefinition(
                key="done", kind=NodeKind.TERMINAL, terminal_status=WorkflowStatus.SUCCEEDED
            ),
        ),
        edges=(EdgeDefinition(source="verify", outcome=NodeOutcome.SUCCESS, target="done"),),
    )
    store.projects[project.id] = project
    store.skills[(skill.key, skill.version)] = skill
    store.phase_packs[(phase_pack.key, phase_pack.version)] = phase_pack
    store.workflow_definitions[(workflow.key, workflow.version)] = workflow
    service = RequestDispatchService(lambda: MemoryUnitOfWork(store))

    options = await service.list_workflow_options(project.id)

    [composition] = options.workflows
    assert options.default_workflow is None
    assert composition.definition == workflow
    assert composition.phase_packs == (phase_pack,)
    assert composition.skills == (skill,)


async def test_dispatch_requires_binding_and_exact_definition() -> None:
    store = MemoryStore()
    project = Project(
        key="unbound-project",
        name="Unbound Project",
        repository_url="https://example.com/unbound.git",
    )
    store.projects[project.id] = project
    service = RequestDispatchService(lambda: MemoryUnitOfWork(store))

    with pytest.raises(ResourceConflict, match="not configured"):
        await service.dispatch(dispatch_command(project, "Cannot start", "missing-binding"))
    with pytest.raises(ResourceNotFound, match="delivery@1"):
        await service.configure_binding(project.id, "delivery", 1)


async def test_dispatch_replays_same_key_and_rejects_different_payload() -> None:
    store = MemoryStore()
    project = Project(
        key="idempotent-project",
        name="Idempotent Project",
        repository_url="https://example.com/idempotent.git",
    )
    store.projects[project.id] = project
    factory = lambda: MemoryUnitOfWork(store)  # noqa: E731
    workflows = WorkflowService(factory)
    service = RequestDispatchService(factory, workflows)
    await workflows.register_definition(definition(1))
    await service.configure_binding(project.id, "delivery", 1)

    first = await service.dispatch(
        dispatch_command(project, "Ship it", "client-request-1", ingress_key="openclaw")
    )
    await workflows.register_definition(definition(2))
    await service.configure_binding(project.id, "delivery", 2)
    event_count = len(store.events)
    replay = await service.dispatch(
        dispatch_command(
            project,
            "  Ship it  ",
            "client-request-1",
            ingress_key="openclaw",
        )
    )

    assert replay.replayed is True
    assert replay.request.id == first.request.id
    assert replay.run.id == first.run.id
    assert replay.workflow.id == first.workflow.id
    assert replay.workflow.snapshot.definition_version == 1
    assert len(store.requests) == 1
    assert len(store.runs) == 1
    assert len(store.workflow_executions) == 1
    assert len(store.events) == event_count

    with pytest.raises(ResourceConflict, match="different request payload"):
        await service.dispatch(
            dispatch_command(
                project,
                "Ship something else",
                "client-request-1",
                ingress_key="openclaw",
            )
        )

    with pytest.raises(ResourceConflict, match="different request payload"):
        await service.dispatch(
            dispatch_command(
                project,
                "Ship it",
                "client-request-1",
                ingress_key="openclaw",
                definition_key="delivery",
                definition_version=2,
            )
        )

    with pytest.raises(ResourceConflict, match="different request payload"):
        await service.dispatch(
            dispatch_command(
                project,
                "Ship it",
                "client-request-1",
                ingress_key="openclaw",
                skill_addons=(
                    NodeSkillAddon(
                        node_key="work",
                        skills=(SkillReference(key="review", version=1),),
                    ),
                ),
            )
        )


async def test_request_override_requires_key_and_version_together() -> None:
    store = MemoryStore()
    project = Project(
        key="invalid-override",
        name="Invalid Override",
        repository_url="https://example.com/invalid.git",
    )
    store.projects[project.id] = project
    service = RequestDispatchService(lambda: MemoryUnitOfWork(store))

    with pytest.raises(ResourceConflict, match="requires definition_key and definition_version"):
        await service.dispatch(
            dispatch_command(
                project,
                "Invalid",
                "invalid-1",
                definition_key="delivery",
            )
        )


async def test_request_skill_addons_are_pinned_without_mutating_definition() -> None:
    store = MemoryStore()
    project = Project(
        key="skill-addon-project",
        name="Skill Add-on Project",
        repository_url="https://example.com/skill-addon.git",
    )
    skill = SkillDefinition(
        key="security-review",
        version=2,
        name="Security Review",
        description="Review security boundaries",
        source_kind=SkillSourceKind.LOCAL,
        source_uri="security-review",
        content_digest=f"sha256:{'b' * 64}",
    )
    store.projects[project.id] = project
    store.skills[(skill.key, skill.version)] = skill
    factory = lambda: MemoryUnitOfWork(store)  # noqa: E731
    workflows = WorkflowService(factory)
    original = await workflows.register_definition(definition(1))
    await RequestDispatchService(factory, workflows).configure_binding(
        project.id, original.key, original.version
    )
    service = RequestDispatchService(factory, workflows)

    dispatched = await service.dispatch(
        dispatch_command(
            project,
            "Review this change",
            "skill-addon-1",
            skill_addons=(NodeSkillAddon(node_key="work", skills=(skill.reference,)),),
        )
    )

    assert dispatched.workflow.snapshot.node("work").skills == (skill.reference,)
    assert dispatched.workflow.snapshot.skills == (skill,)
    assert original.node("work").skills == ()
    assert store.events[-3].payload["skill_addons"] == [
        {
            "node_key": "work",
            "skills": [{"key": "security-review", "version": 2}],
        }
    ]


async def test_request_skill_addons_reject_non_task_and_unknown_nodes() -> None:
    store = MemoryStore()
    project = Project(
        key="invalid-addon-project",
        name="Invalid Add-on Project",
        repository_url="https://example.com/invalid-addon.git",
    )
    skill = SkillDefinition(
        key="review",
        version=1,
        name="Review",
        description="Review output",
        source_kind=SkillSourceKind.LOCAL,
        source_uri="review",
        content_digest=f"sha256:{'c' * 64}",
    )
    store.projects[project.id] = project
    store.skills[(skill.key, skill.version)] = skill
    factory = lambda: MemoryUnitOfWork(store)  # noqa: E731
    workflows = WorkflowService(factory)
    await workflows.register_definition(definition(1))
    await RequestDispatchService(factory, workflows).configure_binding(project.id, "delivery", 1)
    service = RequestDispatchService(factory, workflows)

    for node_key, message in (("done", "require a task node"), ("missing", "not found")):
        with pytest.raises(ResourceConflict, match=message):
            await service.dispatch(
                dispatch_command(
                    project,
                    "Invalid add-on",
                    f"invalid-{node_key}",
                    skill_addons=(NodeSkillAddon(node_key=node_key, skills=(skill.reference,)),),
                )
            )
