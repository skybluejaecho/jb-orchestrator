"""Lease-bounded runtime for durable SCM publication requests."""

import asyncio
from dataclasses import asdict

from jb_orchestrator.application import ExternalExecutionService, ScmPublicationService
from jb_orchestrator.scm.models import (
    ScmPublication,
    ScmPublicationRequest,
    ScmPublicationResult,
)
from jb_orchestrator.scm.registry import ScmPublisherRegistry


class ScmPublicationResultMismatch(ValueError):
    """A publisher returned identifiers that do not match the claimed command."""


class ScmPublicationRuntime:
    """Claim provider-scoped publications and execute installed adapters."""

    def __init__(
        self,
        worker_id: str,
        workspace_scope: str,
        publications: ScmPublicationService,
        executions: ExternalExecutionService,
        publishers: ScmPublisherRegistry,
        *,
        poll_interval_seconds: float = 1.0,
        lease_seconds: int = 300,
        operation_timeout_seconds: float = 240.0,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("SCM publication worker id must not be empty")
        if not workspace_scope.strip():
            raise ValueError("SCM publication workspace scope must not be empty")
        if not publishers.supported_keys:
            raise ValueError("SCM publication worker requires at least one publisher")
        if poll_interval_seconds <= 0 or lease_seconds <= 0 or operation_timeout_seconds <= 0:
            raise ValueError("SCM publication worker intervals must be positive")
        if operation_timeout_seconds >= lease_seconds:
            raise ValueError("SCM publication timeout must be shorter than its lease")
        self._worker_id = worker_id.strip()
        self._workspace_scope = workspace_scope.strip()
        self._publications = publications
        self._executions = executions
        self._publishers = publishers
        self._poll_interval_seconds = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._operation_timeout_seconds = operation_timeout_seconds

    async def run_once(self) -> bool:
        publication = await self._claim_next()
        if publication is None:
            return False
        lease_token = publication.lease_token
        if lease_token is None:  # pragma: no cover - repository contract
            raise RuntimeError("claimed SCM publication has no lease token")
        try:
            execution = await self._executions.get_by_id(publication.external_execution_id)
            if execution.workspace_released_at is not None:
                raise ValueError("managed workspace was released before SCM publication")
            if execution.workspace_scope != self._workspace_scope:
                raise ValueError("external execution workspace scope changed after publication")
            if not execution.workspace_path:
                raise ValueError("external execution has no managed workspace path")
            if execution.workspace_branch != publication.source_branch:
                raise ValueError("external execution branch changed after publication")
            request = ScmPublicationRequest(
                repository=publication.repository,
                workspace_path=execution.workspace_path,
                source_branch=publication.source_branch,
                target_branch=publication.target_branch,
                title=publication.title,
                body=publication.body,
                idempotency_key=publication.idempotency_key,
            )
            result = await asyncio.wait_for(
                self._publishers.publish_review(publication.provider_key, request),
                timeout=self._operation_timeout_seconds,
            )
            self._validate_result(publication, result)
        except Exception as exc:
            await self._publications.fail(
                publication.id, lease_token, str(exc) or type(exc).__name__
            )
        else:
            await self._publications.succeed(publication.id, lease_token, asdict(result))
        return True

    async def run(self) -> None:
        while True:
            if not await self.run_once():
                await asyncio.sleep(self._poll_interval_seconds)

    async def _claim_next(self) -> ScmPublication | None:
        for provider_key in sorted(self._publishers.supported_keys):
            publication = await self._publications.claim_next(
                worker_id=self._worker_id,
                provider_key=provider_key,
                workspace_scope=self._workspace_scope,
                lease_seconds=self._lease_seconds,
            )
            if publication is not None:
                return publication
        return None

    @staticmethod
    def _validate_result(publication: ScmPublication, result: ScmPublicationResult) -> None:
        expected = {
            "provider": publication.provider_key,
            "repository": publication.repository,
            "source_branch": publication.source_branch,
            "target_branch": publication.target_branch,
        }
        mismatches = [
            field_name
            for field_name, value in expected.items()
            if getattr(result, field_name) != value
        ]
        if mismatches:
            raise ScmPublicationResultMismatch(
                "SCM publisher result mismatched: " + ", ".join(mismatches)
            )
