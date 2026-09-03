"""Service-account issuance and bearer-token authentication."""

import hmac
from collections.abc import Callable, Collection
from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.security import ApiPermission, ApiPrincipal, ServiceAccount


@dataclass(frozen=True, slots=True)
class IssuedServiceAccount:
    account: ServiceAccount
    token: str


class SecurityService:
    def __init__(self, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def issue(
        self,
        *,
        key: str,
        name: str,
        permissions: Collection[ApiPermission],
        project_ids: Collection[UUID] = (),
        all_projects: bool = False,
    ) -> IssuedServiceAccount:
        account_id = uuid4()
        token = f"jbsa_{account_id.hex}.{token_urlsafe(32)}"
        account = ServiceAccount(
            id=account_id,
            key=key,
            name=name,
            token_digest=self._token_digest(token),
            permissions=frozenset(permissions),
            project_ids=frozenset(project_ids),
            all_projects=all_projects,
        )
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.service_accounts.get_by_key(account.key) is not None:
                raise ResourceConflict(f"service account key already exists: {account.key}")
            for project_id in account.project_ids:
                if await unit_of_work.projects.get(project_id) is None:
                    raise ResourceNotFound(f"project not found: {project_id}")
            await unit_of_work.service_accounts.add(account)
            await unit_of_work.commit()
        return IssuedServiceAccount(account=account, token=token)

    async def authenticate(self, token: str) -> ApiPrincipal | None:
        account_id = self._account_id(token)
        if account_id is None:
            return None
        async with self._unit_of_work_factory() as unit_of_work:
            account = await unit_of_work.service_accounts.get(account_id)
        if account is None or not account.enabled:
            return None
        if not hmac.compare_digest(account.token_digest, self._token_digest(token)):
            return None
        return ApiPrincipal(
            account_id=account.id,
            account_key=account.key,
            permissions=account.permissions,
            project_ids=account.project_ids,
            all_projects=account.all_projects,
        )

    async def revoke(self, account_id: UUID) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.service_accounts.get(account_id) is None:
                raise ResourceNotFound(f"service account not found: {account_id}")
            await unit_of_work.service_accounts.disable(account_id)
            await unit_of_work.commit()

    async def resolve_project_id(self, resource_type: str, resource_id: UUID) -> UUID | None:
        async with self._unit_of_work_factory() as unit_of_work:
            if resource_type == "project":
                return resource_id if await unit_of_work.projects.get(resource_id) else None
            if resource_type == "request":
                request = await unit_of_work.requests.get(resource_id)
                return request.project_id if request is not None else None
            if resource_type == "run":
                run = await unit_of_work.runs.get(resource_id)
            elif resource_type == "workflow_execution":
                workflow_execution = await unit_of_work.workflow_executions.get(resource_id)
                run = (
                    await unit_of_work.runs.get(workflow_execution.snapshot.run_id)
                    if workflow_execution is not None
                    else None
                )
            elif resource_type == "external_execution":
                external_execution = await unit_of_work.external_executions.get(resource_id)
                run = (
                    await unit_of_work.runs.get(external_execution.run_id)
                    if external_execution is not None
                    else None
                )
            else:
                raise ValueError(f"unknown authorization resource type: {resource_type}")
            if run is None:
                return None
            request = await unit_of_work.requests.get(run.request_id)
            return request.project_id if request is not None else None

    @staticmethod
    def _token_digest(token: str) -> str:
        return f"sha256:{sha256(token.encode()).hexdigest()}"

    @staticmethod
    def _account_id(token: str) -> UUID | None:
        prefix, separator, secret = token.partition(".")
        if separator != "." or not prefix.startswith("jbsa_") or not secret:
            return None
        try:
            return UUID(hex=prefix.removeprefix("jbsa_"))
        except ValueError:
            return None
