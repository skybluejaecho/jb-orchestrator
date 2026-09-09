"""Service-account issuance and bearer-token authentication."""

import hmac
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4

from jb_orchestrator.application.exceptions import ResourceConflict, ResourceNotFound
from jb_orchestrator.application.unit_of_work import UnitOfWork
from jb_orchestrator.security import (
    ApiPermission,
    ApiPrincipal,
    ServiceAccount,
    ServiceAccountCredential,
)


@dataclass(frozen=True, slots=True)
class IssuedServiceAccount:
    account: ServiceAccount
    credential: ServiceAccountCredential
    token: str


@dataclass(frozen=True, slots=True)
class IssuedCredential:
    credential: ServiceAccountCredential
    token: str


class SecurityService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def issue(
        self,
        *,
        key: str,
        name: str,
        permissions: Collection[ApiPermission],
        project_ids: Collection[UUID] = (),
        all_projects: bool = False,
        expires_at: datetime | None = None,
    ) -> IssuedServiceAccount:
        account_id = uuid4()
        issued_at = self._now()
        account = ServiceAccount(
            id=account_id,
            key=key,
            name=name,
            permissions=frozenset(permissions),
            project_ids=frozenset(project_ids),
            all_projects=all_projects,
            created_at=issued_at,
        )
        issued = self._new_credential(account.id, issued_at=issued_at, expires_at=expires_at)
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.service_accounts.get_by_key(account.key) is not None:
                raise ResourceConflict(f"service account key already exists: {account.key}")
            for project_id in account.project_ids:
                if await unit_of_work.projects.get(project_id) is None:
                    raise ResourceNotFound(f"project not found: {project_id}")
            await unit_of_work.service_accounts.add(account)
            await unit_of_work.service_account_credentials.add(issued.credential)
            await unit_of_work.commit()
        return IssuedServiceAccount(
            account=account,
            credential=issued.credential,
            token=issued.token,
        )

    async def issue_credential(
        self, account_id: UUID, *, expires_at: datetime | None = None
    ) -> IssuedCredential:
        issued_at = self._now()
        async with self._unit_of_work_factory() as unit_of_work:
            account = await unit_of_work.service_accounts.get(account_id)
            if account is None:
                raise ResourceNotFound(f"service account not found: {account_id}")
            if not account.enabled:
                raise ResourceConflict("disabled service account cannot receive credentials")
            issued = self._new_credential(
                account.id,
                issued_at=issued_at,
                expires_at=expires_at,
            )
            await unit_of_work.service_account_credentials.add(issued.credential)
            await unit_of_work.commit()
        return issued

    async def list_credentials(self, account_id: UUID) -> list[ServiceAccountCredential]:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.service_accounts.get(account_id) is None:
                raise ResourceNotFound(f"service account not found: {account_id}")
            return await unit_of_work.service_account_credentials.list_for_account(account_id)

    async def authenticate(self, token: str) -> ApiPrincipal | None:
        credential_id = self._credential_id(token)
        if credential_id is None:
            return None
        used_at = self._now()
        async with self._unit_of_work_factory() as unit_of_work:
            credential = await unit_of_work.service_account_credentials.get(credential_id)
            if credential is None or not credential.is_active(used_at):
                return None
            if not hmac.compare_digest(credential.token_digest, self._token_digest(token)):
                return None
            account = await unit_of_work.service_accounts.get(credential.account_id)
            if account is None or not account.enabled:
                return None
            await unit_of_work.service_account_credentials.mark_used(credential.id, used_at)
            await unit_of_work.commit()
            return ApiPrincipal(
                account_id=account.id,
                account_key=account.key,
                permissions=account.permissions,
                project_ids=account.project_ids,
                all_projects=account.all_projects,
                credential_id=credential.id,
            )

    async def revoke_credential(self, account_id: UUID, credential_id: UUID) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.service_accounts.get(account_id) is None:
                raise ResourceNotFound(f"service account not found: {account_id}")
            credential = await unit_of_work.service_account_credentials.get(credential_id)
            if credential is None or credential.account_id != account_id:
                raise ResourceNotFound(f"service account credential not found: {credential_id}")
            if credential.revoked_at is None:
                await unit_of_work.service_account_credentials.revoke(credential_id, self._now())
                await unit_of_work.commit()

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
            elif resource_type == "scm_publication":
                publication = await unit_of_work.scm_publications.get(resource_id)
                external_execution = (
                    await unit_of_work.external_executions.get(publication.external_execution_id)
                    if publication is not None
                    else None
                )
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

    def _new_credential(
        self,
        account_id: UUID,
        *,
        issued_at: datetime,
        expires_at: datetime | None,
    ) -> IssuedCredential:
        credential_id = uuid4()
        token = f"jbsa_{credential_id.hex}.{token_urlsafe(32)}"
        credential = ServiceAccountCredential(
            id=credential_id,
            account_id=account_id,
            token_digest=self._token_digest(token),
            created_at=issued_at,
            expires_at=expires_at,
        )
        return IssuedCredential(credential=credential, token=token)

    @staticmethod
    def _credential_id(token: str) -> UUID | None:
        prefix, separator, secret = token.partition(".")
        if separator != "." or not prefix.startswith("jbsa_") or not secret:
            return None
        try:
            return UUID(hex=prefix.removeprefix("jbsa_"))
        except ValueError:
            return None

    def _now(self) -> datetime:
        value = self._clock()
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
