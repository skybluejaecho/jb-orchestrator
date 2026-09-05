"""Bearer authentication and HTTP authorization policy."""

import re
from dataclasses import dataclass
from uuid import UUID

from fastapi import Request

from jb_orchestrator.application import SecurityService
from jb_orchestrator.security import ApiPermission, ApiPrincipal

RESOURCE_PATH = re.compile(
    r"^/v1/(?P<collection>projects|requests|runs|workflow-executions|external-executions|scm-publications)"
    r"/(?P<id>[0-9a-fA-F-]{36})(?:/|$)"
)
RESOURCE_TYPES = {
    "projects": "project",
    "requests": "request",
    "runs": "run",
    "workflow-executions": "workflow_execution",
    "external-executions": "external_execution",
    "scm-publications": "scm_publication",
}


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    principal: ApiPrincipal | None
    error: str | None = None


async def authenticate_request(request: Request, service: SecurityService) -> AuthenticationResult:
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        return AuthenticationResult(None, "Bearer token is required")
    principal = await service.authenticate(token.strip())
    if principal is None:
        return AuthenticationResult(None, "Bearer token is invalid or revoked")
    return AuthenticationResult(principal)


async def authorize_request(
    request: Request,
    principal: ApiPrincipal,
    service: SecurityService,
) -> bool:
    permission = required_permission(request.method, request.url.path)
    match = RESOURCE_PATH.match(request.url.path)
    if match is None:
        return principal.allows(permission)
    resource_type = RESOURCE_TYPES[match.group("collection")]
    project_id = await service.resolve_project_id(resource_type, UUID(match.group("id")))
    if project_id is None:
        return True
    return principal.allows(permission, project_id)


def required_permission(method: str, path: str) -> ApiPermission:
    if method == "GET":
        return ApiPermission.PROJECT_READ
    if path.endswith("/dispatches") or re.search(r"/projects/[0-9a-fA-F-]{36}/requests$", path):
        return ApiPermission.REQUEST_DISPATCH
    if "/approvals/" in path or path.endswith("/approve"):
        return ApiPermission.WORKFLOW_APPROVE
    if path.endswith("/cancel"):
        return ApiPermission.RUN_CANCEL
    if path.endswith("/workspace-operations"):
        return ApiPermission.WORKSPACE_MANAGE
    if path.endswith("/scm-publications") or (
        "/scm-publications/" in path and path.endswith("/retry")
    ):
        return ApiPermission.SCM_PUBLISH
    return ApiPermission.PROJECT_ADMIN
