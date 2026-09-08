from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from jb_orchestrator.domain import DomainValidationError
from jb_orchestrator.security import (
    ApiPermission,
    ApiPrincipal,
    ServiceAccount,
    ServiceAccountCredential,
)


def test_service_account_requires_explicit_project_scope() -> None:
    with pytest.raises(DomainValidationError, match="project scope"):
        ServiceAccount(
            key="openclaw",
            name="OpenClaw",
            permissions=frozenset({ApiPermission.PROJECT_READ}),
        )


def test_credential_validates_lifecycle_and_active_state() -> None:
    created_at = datetime(2026, 9, 9, tzinfo=UTC)
    credential = ServiceAccountCredential(
        account_id=uuid4(),
        token_digest=f"sha256:{'a' * 64}",
        created_at=created_at,
        expires_at=created_at + timedelta(hours=1),
    )

    assert credential.is_active(created_at + timedelta(minutes=59))
    assert not credential.is_active(created_at + timedelta(hours=1))

    with pytest.raises(DomainValidationError, match="expiration"):
        ServiceAccountCredential(
            account_id=uuid4(),
            token_digest=f"sha256:{'b' * 64}",
            created_at=created_at,
            expires_at=created_at,
        )


def test_principal_checks_permission_and_project_scope() -> None:
    project_id = uuid4()
    principal = ApiPrincipal(
        account_id=uuid4(),
        account_key="openclaw",
        permissions=frozenset({ApiPermission.PROJECT_READ}),
        project_ids=frozenset({project_id}),
        all_projects=False,
    )

    assert principal.allows(ApiPermission.PROJECT_READ, project_id)
    assert not principal.allows(ApiPermission.REQUEST_DISPATCH, project_id)
    assert not principal.allows(ApiPermission.PROJECT_READ, uuid4())
    assert not principal.allows(ApiPermission.PROJECT_READ)
