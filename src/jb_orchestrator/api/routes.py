"""Control-plane REST routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from jb_orchestrator.api.dependencies import (
    get_model_catalog_service,
    get_orchestration_service,
    get_skill_catalog_service,
)
from jb_orchestrator.api.schemas import (
    CreatedRequestResponse,
    ModelProfileCreate,
    ModelProfileResponse,
    ProjectCreate,
    ProjectResponse,
    RunResponse,
    SkillCreate,
    SkillResponse,
    UserRequestCreate,
    UserRequestResponse,
)
from jb_orchestrator.application import (
    CreateUserRequest,
    ModelCatalogService,
    OrchestrationService,
    RegisterProject,
    SkillCatalogService,
)
from jb_orchestrator.model_routing import ModelProfile
from jb_orchestrator.skills import SkillDefinition

router = APIRouter(prefix="/v1")
Service = Annotated[OrchestrationService, Depends(get_orchestration_service)]
SkillService = Annotated[SkillCatalogService, Depends(get_skill_catalog_service)]
ModelService = Annotated[ModelCatalogService, Depends(get_model_catalog_service)]


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
