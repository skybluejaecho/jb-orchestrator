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
from jb_orchestrator.domain import DomainEvent
from jb_orchestrator.security import (
    ApiPermission,
    ApiPrincipal,
    CredentialReadinessStatus,
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


@dataclass(frozen=True, slots=True)
class CredentialInventorySummary:
    total: int
    active: int
    usable: int
    expired: int
    revoked: int
    latest_created_at: datetime | None
    last_used_at: datetime | None


@dataclass(frozen=True, slots=True)
class ServiceAccountInventory:
    account: ServiceAccount
    credential_summary: CredentialInventorySummary


@dataclass(frozen=True, slots=True)
class CredentialReadiness:
    account: ServiceAccount
    status: CredentialReadinessStatus
    credential_summary: CredentialInventorySummary
    next_expires_at: datetime | None
    checked_at: datetime
    warning_seconds: int


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
            await unit_of_work.events.append(
                self._credential_event(
                    account_id=account.id,
                    credential=issued.credential,
                    event_type="service_account.credential_issued",
                    occurred_at=issued_at,
                    actor=None,
                )
            )
            await unit_of_work.commit()
        return IssuedServiceAccount(
            account=account,
            credential=issued.credential,
            token=issued.token,
        )

    async def issue_credential(
        self,
        account_id: UUID,
        *,
        expires_at: datetime | None = None,
        actor: ApiPrincipal | None = None,
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
            await unit_of_work.events.append(
                self._credential_event(
                    account_id=account.id,
                    credential=issued.credential,
                    event_type="service_account.credential_issued",
                    occurred_at=issued_at,
                    actor=actor,
                )
            )
            await unit_of_work.commit()
        return issued

    async def list_credentials(self, account_id: UUID) -> list[ServiceAccountCredential]:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.service_accounts.get(account_id) is None:
                raise ResourceNotFound(f"service account not found: {account_id}")
            return await unit_of_work.service_account_credentials.list_for_account(account_id)

    async def list_account_inventory(
        self,
        *,
        enabled: bool | None = None,
        key_prefix: str | None = None,
        after_key: str | None = None,
        limit: int = 100,
    ) -> list[ServiceAccountInventory]:
        checked_at = self._now()
        async with self._unit_of_work_factory() as unit_of_work:
            accounts = await unit_of_work.service_accounts.list(
                enabled=enabled,
                key_prefix=key_prefix,
                after_key=after_key,
                limit=limit,
            )
            credentials = await unit_of_work.service_account_credentials.list_for_accounts(
                frozenset(account.id for account in accounts)
            )
        credentials_by_account: dict[UUID, list[ServiceAccountCredential]] = {
            account.id: [] for account in accounts
        }
        for credential in credentials:
            credentials_by_account[credential.account_id].append(credential)
        return [
            self._account_inventory(
                account,
                credentials_by_account[account.id],
                checked_at=checked_at,
            )
            for account in accounts
        ]

    async def get_account_inventory(self, account_id: UUID) -> ServiceAccountInventory:
        checked_at = self._now()
        async with self._unit_of_work_factory() as unit_of_work:
            account = await unit_of_work.service_accounts.get(account_id)
            if account is None:
                raise ResourceNotFound(f"service account not found: {account_id}")
            credentials = await unit_of_work.service_account_credentials.list_for_account(
                account_id
            )
        return self._account_inventory(account, credentials, checked_at=checked_at)

    async def list_credential_readiness(
        self,
        *,
        warning_seconds: int,
        issues_only: bool = False,
        key_prefix: str | None = None,
        after_key: str | None = None,
        limit: int = 100,
    ) -> list[CredentialReadiness]:
        if warning_seconds <= 0:
            raise ValueError("credential readiness warning must be greater than zero")
        if limit <= 0:
            raise ValueError("credential readiness limit must be greater than zero")
        checked_at = self._now()
        results: list[CredentialReadiness] = []
        cursor = after_key
        async with self._unit_of_work_factory() as unit_of_work:
            while len(results) < limit:
                accounts = await unit_of_work.service_accounts.list(
                    key_prefix=key_prefix,
                    after_key=cursor,
                    limit=500,
                )
                if not accounts:
                    break
                credentials = await unit_of_work.service_account_credentials.list_for_accounts(
                    frozenset(account.id for account in accounts)
                )
                credentials_by_account: dict[UUID, list[ServiceAccountCredential]] = {
                    account.id: [] for account in accounts
                }
                for credential in credentials:
                    credentials_by_account[credential.account_id].append(credential)
                for account in accounts:
                    readiness = self._credential_readiness(
                        account,
                        credentials_by_account[account.id],
                        checked_at=checked_at,
                        warning_seconds=warning_seconds,
                    )
                    if not issues_only or readiness.status is not CredentialReadinessStatus.HEALTHY:
                        results.append(readiness)
                        if len(results) == limit:
                            return results
                if len(accounts) < 500:
                    break
                cursor = accounts[-1].key
        return results

    async def get_credential_readiness(
        self,
        account_id: UUID,
        *,
        warning_seconds: int,
    ) -> CredentialReadiness:
        if warning_seconds <= 0:
            raise ValueError("credential readiness warning must be greater than zero")
        checked_at = self._now()
        async with self._unit_of_work_factory() as unit_of_work:
            account = await unit_of_work.service_accounts.get(account_id)
            if account is None:
                raise ResourceNotFound(f"service account not found: {account_id}")
            credentials = await unit_of_work.service_account_credentials.list_for_account(
                account_id
            )
        return self._credential_readiness(
            account,
            credentials,
            checked_at=checked_at,
            warning_seconds=warning_seconds,
        )

    async def list_credential_events(
        self,
        account_id: UUID,
        *,
        before_sequence: int | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.service_accounts.get(account_id) is None:
                raise ResourceNotFound(f"service account not found: {account_id}")
            return await unit_of_work.events.list_aggregate(
                aggregate_type="service_account",
                aggregate_id=account_id,
                before_sequence=before_sequence,
                limit=limit,
            )

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

    async def revoke_credential(
        self,
        account_id: UUID,
        credential_id: UUID,
        *,
        actor: ApiPrincipal | None = None,
    ) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            if await unit_of_work.service_accounts.get(account_id) is None:
                raise ResourceNotFound(f"service account not found: {account_id}")
            credential = await unit_of_work.service_account_credentials.get(credential_id)
            if credential is None or credential.account_id != account_id:
                raise ResourceNotFound(f"service account credential not found: {credential_id}")
            if credential.revoked_at is None:
                revoked_at = self._now()
                await unit_of_work.service_account_credentials.revoke(credential_id, revoked_at)
                await unit_of_work.events.append(
                    self._credential_event(
                        account_id=account_id,
                        credential=credential,
                        event_type="service_account.credential_revoked",
                        occurred_at=revoked_at,
                        actor=actor,
                    )
                )
                await unit_of_work.commit()

    async def revoke(self, account_id: UUID, *, actor: ApiPrincipal | None = None) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            account = await unit_of_work.service_accounts.get(account_id)
            if account is None:
                raise ResourceNotFound(f"service account not found: {account_id}")
            if account.enabled:
                revoked_at = self._now()
                await unit_of_work.service_accounts.disable(account_id)
                await unit_of_work.events.append(
                    DomainEvent(
                        aggregate_type="service_account",
                        aggregate_id=account_id,
                        event_type="service_account.revoked",
                        occurred_at=revoked_at,
                        payload=self._actor_payload(actor),
                    )
                )
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
    def _credential_event(
        *,
        account_id: UUID,
        credential: ServiceAccountCredential,
        event_type: str,
        occurred_at: datetime,
        actor: ApiPrincipal | None,
    ) -> DomainEvent:
        return DomainEvent(
            aggregate_type="service_account",
            aggregate_id=account_id,
            event_type=event_type,
            occurred_at=occurred_at,
            payload={
                "credential_id": str(credential.id),
                "expires_at": (
                    credential.expires_at.isoformat() if credential.expires_at is not None else None
                ),
                **SecurityService._actor_payload(actor),
            },
        )

    @staticmethod
    def _account_inventory(
        account: ServiceAccount,
        credentials: Collection[ServiceAccountCredential],
        *,
        checked_at: datetime,
    ) -> ServiceAccountInventory:
        return ServiceAccountInventory(
            account=account,
            credential_summary=SecurityService._credential_summary(
                account,
                credentials,
                checked_at=checked_at,
            ),
        )

    @staticmethod
    def _credential_summary(
        account: ServiceAccount,
        credentials: Collection[ServiceAccountCredential],
        *,
        checked_at: datetime,
    ) -> CredentialInventorySummary:
        active = sum(credential.is_active(checked_at) for credential in credentials)
        revoked = sum(credential.revoked_at is not None for credential in credentials)
        expired = sum(
            credential.revoked_at is None
            and credential.expires_at is not None
            and credential.expires_at <= checked_at
            for credential in credentials
        )
        created_values = [credential.created_at for credential in credentials]
        used_values = [
            credential.last_used_at
            for credential in credentials
            if credential.last_used_at is not None
        ]
        return CredentialInventorySummary(
            total=len(credentials),
            active=active,
            usable=active if account.enabled else 0,
            expired=expired,
            revoked=revoked,
            latest_created_at=max(created_values, default=None),
            last_used_at=max(used_values, default=None),
        )

    @staticmethod
    def _credential_readiness(
        account: ServiceAccount,
        credentials: Collection[ServiceAccountCredential],
        *,
        checked_at: datetime,
        warning_seconds: int,
    ) -> CredentialReadiness:
        summary = SecurityService._credential_summary(
            account,
            credentials,
            checked_at=checked_at,
        )
        active_expirations = [
            credential.expires_at
            for credential in credentials
            if credential.is_active(checked_at) and credential.expires_at is not None
        ]
        next_expires_at = min(active_expirations, default=None)
        if not account.enabled:
            status = CredentialReadinessStatus.ACCOUNT_DISABLED
        elif summary.usable == 0 and summary.expired > 0:
            status = CredentialReadinessStatus.EXPIRED
        elif summary.usable == 0:
            status = CredentialReadinessStatus.NO_USABLE_CREDENTIAL
        elif (
            next_expires_at is not None
            and (next_expires_at - checked_at).total_seconds() <= warning_seconds
        ):
            status = CredentialReadinessStatus.EXPIRING_SOON
        else:
            status = CredentialReadinessStatus.HEALTHY
        return CredentialReadiness(
            account=account,
            status=status,
            credential_summary=summary,
            next_expires_at=next_expires_at,
            checked_at=checked_at,
            warning_seconds=warning_seconds,
        )

    @staticmethod
    def _actor_payload(actor: ApiPrincipal | None) -> dict[str, str | None]:
        return {
            "actor_account_id": str(actor.account_id) if actor is not None else None,
            "actor_credential_id": (
                str(actor.credential_id)
                if actor is not None and actor.credential_id is not None
                else None
            ),
        }

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
