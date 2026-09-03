"""Control-plane REST routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import StreamingResponse

from jb_orchestrator.api.dependencies import (
    get_budget_service,
    get_external_execution_service,
    get_model_catalog_service,
    get_orchestration_service,
    get_skill_catalog_service,
    get_workflow_service,
)
from jb_orchestrator.api.event_streams import external_execution_event_stream
from jb_orchestrator.api.schemas import (
    BudgetConfigure,
    BudgetResponse,
    CreatedRequestResponse,
    ExternalExecutionResponse,
    ModelProfileCreate,
    ModelProfileResponse,
    NodeExecutionResponse,
    ProjectCreate,
    ProjectResponse,
    RunResponse,
    SkillCreate,
    SkillResponse,
    UsageRecordResponse,
    UserRequestCreate,
    UserRequestResponse,
    WorkflowApprovalResolve,
    WorkflowDefinitionCreate,
    WorkflowDefinitionResponse,
    WorkflowEdgePayload,
    WorkflowExecutionResponse,
    WorkflowNodePayload,
    WorkflowStart,
)
from jb_orchestrator.application import (
    BudgetService,
    CreateUserRequest,
    ExternalExecutionService,
    ModelCatalogService,
    OrchestrationService,
    RegisterProject,
    SkillCatalogService,
    WorkflowService,
)
from jb_orchestrator.config import get_settings
from jb_orchestrator.domain import DomainValidationError
from jb_orchestrator.external_executions import ExternalExecutionStatus
from jb_orchestrator.model_routing import ModelProfile, ModelRoutingRequest
from jb_orchestrator.skills import SkillDefinition, SkillReference
from jb_orchestrator.workflows import (
    EdgeDefinition,
    NodeDefinition,
    WorkflowDefinition,
    WorkflowExecution,
)

router = APIRouter(prefix="/v1")
Service = Annotated[OrchestrationService, Depends(get_orchestration_service)]
SkillService = Annotated[SkillCatalogService, Depends(get_skill_catalog_service)]
ModelService = Annotated[ModelCatalogService, Depends(get_model_catalog_service)]
BudgetServiceDependency = Annotated[BudgetService, Depends(get_budget_service)]
WorkflowServiceDependency = Annotated[WorkflowService, Depends(get_workflow_service)]
ExternalExecutionServiceDependency = Annotated[
    ExternalExecutionService, Depends(get_external_execution_service)
]


def workflow_definition_response(
    definition: WorkflowDefinition,
) -> WorkflowDefinitionResponse:
    return WorkflowDefinitionResponse(
        id=definition.id,
        key=definition.key,
        version=definition.version,
        entry_node=definition.entry_node,
        nodes=tuple(WorkflowNodePayload.model_validate(node) for node in definition.nodes),
        edges=tuple(WorkflowEdgePayload.model_validate(edge) for edge in definition.edges),
    )


def workflow_execution_response(execution: WorkflowExecution) -> WorkflowExecutionResponse:
    return WorkflowExecutionResponse(
        id=execution.id,
        run_id=execution.snapshot.run_id,
        snapshot_id=execution.snapshot.id,
        definition_key=execution.snapshot.definition_key,
        definition_version=execution.snapshot.definition_version,
        status=execution.status,
        nodes=tuple(
            NodeExecutionResponse.model_validate(execution.nodes[node.key])
            for node in execution.snapshot.nodes
        ),
        failure_reason=execution.failure_reason,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        updated_at=execution.updated_at,
        version=execution.version,
    )


def workflow_definition_from_payload(
    payload: WorkflowDefinitionCreate,
) -> WorkflowDefinition:
    return WorkflowDefinition(
        key=payload.key,
        version=payload.version,
        entry_node=payload.entry_node,
        nodes=tuple(
            NodeDefinition(
                key=node.key,
                kind=node.kind,
                max_attempts=node.max_attempts,
                max_visits=node.max_visits,
                timeout_seconds=node.timeout_seconds,
                terminal_status=node.terminal_status,
                executor_key=node.executor_key,
                instructions=node.instructions,
                configuration=node.configuration,
                skills=tuple(
                    SkillReference(key=reference.key, version=reference.version)
                    for reference in node.skills
                ),
                model_routing=(
                    ModelRoutingRequest(**node.model_routing.model_dump())
                    if node.model_routing is not None
                    else None
                ),
            )
            for node in payload.nodes
        ),
        edges=tuple(
            EdgeDefinition(source=edge.source, outcome=edge.outcome, target=edge.target)
            for edge in payload.edges
        ),
    )


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def register_project(payload: ProjectCreate, service: Service) -> ProjectResponse:
    project = await service.register_project(
        RegisterProject(
            key=payload.key,
            name=payload.name,
            repository_url=str(payload.repository_url),
            default_branch=payload.default_branch,
        )
    )
    return ProjectResponse.model_validate(project)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID, service: Service) -> ProjectResponse:
    return ProjectResponse.model_validate(await service.get_project(project_id))


@router.post(
    "/projects/{project_id}/requests",
    response_model=CreatedRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_request(
    project_id: UUID, payload: UserRequestCreate, service: Service
) -> CreatedRequestResponse:
    created = await service.create_request(
        CreateUserRequest(project_id=project_id, prompt=payload.prompt, title=payload.title)
    )
    return CreatedRequestResponse(
        request=UserRequestResponse.model_validate(created.request),
        run=RunResponse.model_validate(created.run),
    )


@router.get("/requests/{request_id}", response_model=UserRequestResponse)
async def get_request(request_id: UUID, service: Service) -> UserRequestResponse:
    return UserRequestResponse.model_validate(await service.get_request(request_id))


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: UUID, service: Service) -> RunResponse:
    return RunResponse.model_validate(await service.get_run(run_id))


@router.post("/runs/{run_id}/approve", response_model=RunResponse)
async def approve_run(run_id: UUID, service: Service) -> RunResponse:
    return RunResponse.model_validate(await service.approve_run(run_id))


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(run_id: UUID, service: Service) -> RunResponse:
    return RunResponse.model_validate(await service.cancel_run(run_id))


@router.post(
    "/workflows",
    response_model=WorkflowDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_workflow(
    payload: WorkflowDefinitionCreate,
    service: WorkflowServiceDependency,
) -> WorkflowDefinitionResponse:
    definition = await service.register_definition(workflow_definition_from_payload(payload))
    return workflow_definition_response(definition)


@router.get("/workflows", response_model=list[WorkflowDefinitionResponse])
async def list_workflows(
    service: WorkflowServiceDependency,
) -> list[WorkflowDefinitionResponse]:
    return [
        workflow_definition_response(definition)
        for definition in await service.list_latest_definitions()
    ]


@router.get("/workflows/{key}", response_model=WorkflowDefinitionResponse)
async def get_workflow(
    key: str,
    service: WorkflowServiceDependency,
    version: int | None = None,
) -> WorkflowDefinitionResponse:
    return workflow_definition_response(await service.get_definition(key, version))


@router.post(
    "/runs/{run_id}/workflow",
    response_model=WorkflowExecutionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_workflow(
    run_id: UUID,
    payload: WorkflowStart,
    service: WorkflowServiceDependency,
) -> WorkflowExecutionResponse:
    execution = await service.start(run_id, payload.definition_key, payload.version)
    return workflow_execution_response(execution)


@router.get("/runs/{run_id}/workflow", response_model=WorkflowExecutionResponse)
async def get_run_workflow(
    run_id: UUID,
    service: WorkflowServiceDependency,
) -> WorkflowExecutionResponse:
    return workflow_execution_response(await service.get_by_run(run_id))


@router.get("/workflow-executions/{execution_id}", response_model=WorkflowExecutionResponse)
async def get_workflow_execution(
    execution_id: UUID,
    service: WorkflowServiceDependency,
) -> WorkflowExecutionResponse:
    return workflow_execution_response(await service.get(execution_id))


@router.post(
    "/workflow-executions/{execution_id}/approvals/{node_key}",
    response_model=WorkflowExecutionResponse,
)
async def resolve_workflow_approval(
    execution_id: UUID,
    node_key: str,
    payload: WorkflowApprovalResolve,
    service: WorkflowServiceDependency,
) -> WorkflowExecutionResponse:
    execution = await service.resolve_approval(
        execution_id,
        node_key,
        approved=payload.approved,
    )
    return workflow_execution_response(execution)


@router.post(
    "/workflow-executions/{execution_id}/cancel",
    response_model=WorkflowExecutionResponse,
)
async def cancel_workflow_execution(
    execution_id: UUID,
    service: WorkflowServiceDependency,
) -> WorkflowExecutionResponse:
    return workflow_execution_response(await service.cancel(execution_id))


@router.post("/skills", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def register_skill(payload: SkillCreate, service: SkillService) -> SkillResponse:
    skill = await service.register(SkillDefinition(**payload.model_dump()))
    return SkillResponse.model_validate(skill)


@router.get("/skills", response_model=list[SkillResponse])
async def list_skills(service: SkillService) -> list[SkillResponse]:
    return [SkillResponse.model_validate(skill) for skill in await service.list_latest()]


@router.get("/skills/{key}", response_model=SkillResponse)
async def get_skill(key: str, service: SkillService, version: int | None = None) -> SkillResponse:
    return SkillResponse.model_validate(await service.get(key, version))


@router.post("/models", response_model=ModelProfileResponse, status_code=status.HTTP_201_CREATED)
async def register_model(
    payload: ModelProfileCreate, service: ModelService
) -> ModelProfileResponse:
    profile = await service.register(ModelProfile(**payload.model_dump()))
    return ModelProfileResponse.model_validate(profile)


@router.get("/models", response_model=list[ModelProfileResponse])
async def list_models(service: ModelService) -> list[ModelProfileResponse]:
    return [ModelProfileResponse.model_validate(value) for value in await service.list_latest()]


@router.get("/models/{key}", response_model=ModelProfileResponse)
async def get_model(
    key: str, service: ModelService, version: int | None = None
) -> ModelProfileResponse:
    return ModelProfileResponse.model_validate(await service.get(key, version))


@router.put("/projects/{project_id}/budget", response_model=BudgetResponse)
async def configure_budget(
    project_id: UUID,
    payload: BudgetConfigure,
    service: BudgetServiceDependency,
) -> BudgetResponse:
    return BudgetResponse.model_validate(await service.configure(project_id, payload.limit_usd))


@router.get("/projects/{project_id}/budget", response_model=BudgetResponse)
async def get_budget(project_id: UUID, service: BudgetServiceDependency) -> BudgetResponse:
    return BudgetResponse.model_validate(await service.get(project_id))


@router.get("/projects/{project_id}/usage", response_model=list[UsageRecordResponse])
async def list_usage(
    project_id: UUID, service: BudgetServiceDependency
) -> list[UsageRecordResponse]:
    return [
        UsageRecordResponse.model_validate(record)
        for record in await service.list_usage(project_id)
    ]


@router.get("/external-executions", response_model=list[ExternalExecutionResponse])
async def list_external_executions(
    service: ExternalExecutionServiceDependency,
    workflow_execution_id: UUID | None = None,
    run_id: UUID | None = None,
    status: ExternalExecutionStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ExternalExecutionResponse]:
    return [
        ExternalExecutionResponse.model_validate(execution)
        for execution in await service.list(
            workflow_execution_id=workflow_execution_id,
            run_id=run_id,
            status=status,
            limit=limit,
        )
    ]


@router.get("/external-executions/events/stream")
async def stream_external_execution_events(
    request: Request,
    service: ExternalExecutionServiceDependency,
    after: Annotated[UUID | None, Query()] = None,
    last_event_id: Annotated[UUID | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    if after is not None and last_event_id is not None and after != last_event_id:
        raise DomainValidationError("after and Last-Event-ID cursors must match")
    cursor = last_event_id or after
    initial_events = await service.list_events(after_event_id=cursor)
    settings = get_settings()
    return StreamingResponse(
        external_execution_event_stream(
            request=request,
            service=service,
            initial_events=initial_events,
            cursor=cursor,
            poll_interval_seconds=settings.sse_poll_interval_seconds,
            heartbeat_interval_seconds=settings.sse_heartbeat_interval_seconds,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/external-executions/{execution_id}", response_model=ExternalExecutionResponse)
async def get_external_execution(
    execution_id: UUID,
    service: ExternalExecutionServiceDependency,
) -> ExternalExecutionResponse:
    return ExternalExecutionResponse.model_validate(await service.get_by_id(execution_id))
