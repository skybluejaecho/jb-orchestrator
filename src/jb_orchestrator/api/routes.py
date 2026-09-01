"""Control-plane REST routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from jb_orchestrator.api.dependencies import get_orchestration_service
from jb_orchestrator.api.schemas import (
    CreatedRequestResponse,
    ProjectCreate,
    ProjectResponse,
    RunResponse,
    UserRequestCreate,
    UserRequestResponse,
)
from jb_orchestrator.application import CreateUserRequest, OrchestrationService, RegisterProject

router = APIRouter(prefix="/v1")
Service = Annotated[OrchestrationService, Depends(get_orchestration_service)]


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
