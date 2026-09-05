"""Application service for durable SCM publication requests."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.domain import DomainEvent, DomainValidationError, Project
from jb_orchestrator.external_executions import ExternalExecution
from jb_orchestrator.scm import (
    ScmPublication,
    ScmPublicationFailureCode,
    ScmPublicationStatus,
)


class ScmPublicationService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def request(
        self,
        external_execution_id: UUID,
        *,
        provider_key: str,
        target_branch: str,
        title: str,
        body: str,
        idempotency_key: str,
        requested_by: str,
    ) -> tuple[ScmPublication, bool]:
        normalized_key = idempotency_key.strip()
        if not normalized_key:
            raise DomainValidationError("SCM publication idempotency key must not be empty")
        async with self._unit_of_work_factory() as unit_of_work:
            execution = await self._execution(unit_of_work, external_execution_id)
            if not execution.is_terminal:
                raise ResourceConflict("SCM publication requires a terminal external execution")
            if execution.workspace_released_at is not None:
                raise ResourceConflict("SCM publication requires an unreleased workspace")
            if not execution.workspace_branch or not execution.workspace_scope:
                raise ResourceConflict("external execution has no managed workspace scope")
            project = await self._project(unit_of_work, execution)
            values = {
                "provider_key": provider_key.strip(),
                "repository": project.repository_url,
                "source_branch": execution.workspace_branch,
                "target_branch": target_branch.strip(),
                "title": title.strip(),
                "body": body.strip(),
            }
            existing = await unit_of_work.scm_publications.get_by_idempotency_key(
                external_execution_id, normalized_key
            )
            if existing is not None:
                if any(getattr(existing, key) != value for key, value in values.items()):
                    raise ResourceConflict(
                        "idempotency key was already used for another publication"
                    )
                return existing, True
            publication = ScmPublication(
                external_execution_id=external_execution_id,
                provider_key=values["provider_key"],
                repository=values["repository"],
                source_branch=values["source_branch"],
                target_branch=values["target_branch"],
                title=values["title"],
                body=values["body"],
                workspace_scope=execution.workspace_scope,
                idempotency_key=normalized_key,
                requested_by=requested_by,
            )
            if not await unit_of_work.scm_publications.try_add(publication):
                existing = await unit_of_work.scm_publications.get_by_idempotency_key(
                    external_execution_id, normalized_key
                )
                if existing is None:  # pragma: no cover - database invariant
                    raise RuntimeError("SCM publication idempotency claim disappeared")
                if any(getattr(existing, key) != value for key, value in values.items()):
                    raise ResourceConflict(
                        "idempotency key was already used for another publication"
                    )
                return existing, True
            await self._event(unit_of_work, publication, execution, "scm_publication.requested")
            await unit_of_work.commit()
            return publication, False

    async def list_for_execution(
        self, external_execution_id: UUID, *, limit: int = 100
    ) -> list[ScmPublication]:
        async with self._unit_of_work_factory() as unit_of_work:
            await self._execution(unit_of_work, external_execution_id)
            return await unit_of_work.scm_publications.list_for_execution(
                external_execution_id, limit=limit
            )

    async def retry(
        self, publication_id: UUID, *, requested_by: str
    ) -> tuple[ScmPublication, bool]:
        async with self._unit_of_work_factory() as unit_of_work:
            publication = await unit_of_work.scm_publications.get(publication_id, for_update=True)
            if publication is None:
                raise ResourceNotFound(f"SCM publication not found: {publication_id}")
            execution = await self._execution(unit_of_work, publication.external_execution_id)
            if execution.workspace_released_at is not None:
                raise ResourceConflict("SCM publication retry requires an unreleased workspace")
            if execution.workspace_branch != publication.source_branch:
                raise ResourceConflict("SCM publication source branch changed before retry")
            if publication.status in {
                ScmPublicationStatus.PENDING,
                ScmPublicationStatus.CLAIMED,
            }:
                return publication, True
            if publication.status is ScmPublicationStatus.SUCCEEDED:
                raise ResourceConflict("succeeded SCM publication cannot be retried")
            publication.retry()
            await unit_of_work.scm_publications.save(publication)
            await self._event(
                unit_of_work,
                publication,
                execution,
                "scm_publication.retried",
                actor=requested_by.strip() or "anonymous",
            )
            await unit_of_work.commit()
            return publication, False

    async def claim_next(
        self,
        *,
        worker_id: str,
        provider_key: str,
        workspace_scope: str,
        lease_seconds: int = 300,
    ) -> ScmPublication | None:
        async with self._unit_of_work_factory() as unit_of_work:
            publication = await unit_of_work.scm_publications.claim_next(
                worker_id=worker_id,
                provider_key=provider_key,
                workspace_scope=workspace_scope,
                lease_seconds=lease_seconds,
            )
            if publication is None:
                return None
            execution = await self._execution(unit_of_work, publication.external_execution_id)
            await self._event(unit_of_work, publication, execution, "scm_publication.claimed")
            await unit_of_work.commit()
            return publication

    async def succeed(
        self, publication_id: UUID, lease_token: UUID, result: dict[str, Any]
    ) -> ScmPublication:
        return await self._finish(publication_id, lease_token, result=result)

    async def fail(
        self,
        publication_id: UUID,
        lease_token: UUID,
        reason: str,
        *,
        code: ScmPublicationFailureCode = ScmPublicationFailureCode.UNEXPECTED,
        retryable: bool = False,
    ) -> ScmPublication:
        return await self._finish(
            publication_id,
            lease_token,
            failure_reason=reason,
            failure_code=code,
            failure_retryable=retryable,
        )

    async def _finish(
        self,
        publication_id: UUID,
        lease_token: UUID,
        *,
        result: dict[str, Any] | None = None,
        failure_reason: str | None = None,
        failure_code: ScmPublicationFailureCode | None = None,
        failure_retryable: bool = False,
    ) -> ScmPublication:
        async with self._unit_of_work_factory() as unit_of_work:
            publication = await unit_of_work.scm_publications.get(publication_id, for_update=True)
            if publication is None:
                raise ResourceNotFound(f"SCM publication not found: {publication_id}")
            if failure_reason is None:
                publication.succeed(lease_token, result or {})
                event_type = "scm_publication.succeeded"
            else:
                publication.fail(
                    lease_token,
                    failure_reason,
                    code=failure_code or ScmPublicationFailureCode.UNEXPECTED,
                    retryable=failure_retryable,
                )
                event_type = "scm_publication.failed"
            await unit_of_work.scm_publications.save(publication)
            execution = await self._execution(unit_of_work, publication.external_execution_id)
            await self._event(unit_of_work, publication, execution, event_type)
            await unit_of_work.commit()
            return publication

    @staticmethod
    async def _execution(unit_of_work: UnitOfWork, execution_id: UUID) -> ExternalExecution:
        execution = await unit_of_work.external_executions.get(execution_id)
        if execution is None:
            raise ResourceNotFound(f"external execution not found: {execution_id}")
        return execution

    @staticmethod
    async def _project(unit_of_work: UnitOfWork, execution: ExternalExecution) -> Project:
        run = await unit_of_work.runs.get(execution.run_id)
        if run is None:
            raise ResourceNotFound(f"run not found: {execution.run_id}")
        request = await unit_of_work.requests.get(run.request_id)
        if request is None:
            raise ResourceNotFound(f"request not found: {run.request_id}")
        project = await unit_of_work.projects.get(request.project_id)
        if project is None:
            raise ResourceNotFound(f"project not found: {request.project_id}")
        return project

    @staticmethod
    async def _event(
        unit_of_work: UnitOfWork,
        publication: ScmPublication,
        execution: ExternalExecution,
        event_type: str,
        actor: str | None = None,
    ) -> None:
        payload = {
            "external_execution_id": str(execution.id),
            "workflow_execution_id": str(execution.execution_id),
            "run_id": str(execution.run_id),
            "provider_key": publication.provider_key,
            "repository": publication.repository,
            "source_branch": publication.source_branch,
            "target_branch": publication.target_branch,
            "status": publication.status.value,
            "worker_id": publication.worker_id,
            "failure_reason": publication.failure_reason,
            "failure_code": publication.failure_code.value if publication.failure_code else None,
            "failure_retryable": publication.failure_retryable,
            "attempt_count": publication.attempt_count,
        }
        if actor is not None:
            payload["actor"] = actor
        await unit_of_work.events.append(
            DomainEvent(
                aggregate_type="scm_publication",
                aggregate_id=publication.id,
                event_type=event_type,
                payload=payload,
            )
        )
