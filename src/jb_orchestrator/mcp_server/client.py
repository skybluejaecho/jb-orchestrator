"""Authenticated HTTP client used by MCP tools."""

from typing import Any, cast
from uuid import UUID

import httpx

from jb_orchestrator.config import Settings, get_settings

JsonObject = dict[str, Any]
JsonPayload = JsonObject | list[Any]


class ControlPlaneError(RuntimeError):
    """A safe control-plane failure suitable for an MCP tool result."""


class ControlPlaneClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._transport = transport
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ControlPlaneClient":
        settings = settings or get_settings()
        token = settings.api_token.get_secret_value() if settings.api_token is not None else None
        return cls(base_url=settings.control_plane_url, token=token)

    @property
    def authenticated(self) -> bool:
        return bool(self._token)

    async def get_project(self, project_id: UUID) -> JsonObject:
        return cast(JsonObject, await self._request("GET", f"/v1/projects/{project_id}"))

    async def list_project_requests(
        self, project_id: UUID, *, status: str | None = None, limit: int = 20
    ) -> list[Any]:
        return cast(
            list[Any],
            await self._request(
                "GET",
                f"/v1/projects/{project_id}/requests",
                params=self._query(status=status, limit=limit),
            ),
        )

    async def list_project_workflows(
        self, project_id: UUID, *, status: str | None = None, limit: int = 20
    ) -> list[Any]:
        return cast(
            list[Any],
            await self._request(
                "GET",
                f"/v1/projects/{project_id}/workflow-executions",
                params=self._query(status=status, limit=limit),
            ),
        )

    async def list_workflow_options(self, project_id: UUID) -> JsonObject:
        return cast(
            JsonObject,
            await self._request("GET", f"/v1/projects/{project_id}/workflow-options"),
        )

    async def dispatch_request(
        self,
        project_id: UUID,
        *,
        prompt: str,
        idempotency_key: str,
        title: str | None = None,
        external_request_id: str | None = None,
        actor_id: str | None = None,
        conversation_id: str | None = None,
        definition_key: str | None = None,
        definition_version: int | None = None,
    ) -> JsonObject:
        if (definition_key is None) != (definition_version is None):
            raise ControlPlaneError(
                "workflow override requires definition_key and definition_version"
            )
        headers = {
            "Idempotency-Key": idempotency_key,
            "X-JB-Ingress-Key": "mcp",
            "X-JB-External-Request-ID": external_request_id or idempotency_key,
        }
        if actor_id is not None:
            headers["X-JB-Actor-ID"] = actor_id
        if conversation_id is not None:
            headers["X-JB-Conversation-ID"] = conversation_id
        return cast(
            JsonObject,
            await self._request(
                "POST",
                f"/v1/projects/{project_id}/dispatches",
                payload={
                    "prompt": prompt,
                    "title": title,
                    "workflow": (
                        {
                            "definition_key": definition_key,
                            "definition_version": definition_version,
                        }
                        if definition_key is not None and definition_version is not None
                        else None
                    ),
                },
                headers=headers,
            ),
        )

    async def get_request(self, request_id: UUID) -> JsonObject:
        return cast(JsonObject, await self._request("GET", f"/v1/requests/{request_id}"))

    async def get_run(self, run_id: UUID) -> JsonObject:
        return cast(JsonObject, await self._request("GET", f"/v1/runs/{run_id}"))

    async def get_workflow_execution(self, execution_id: UUID) -> JsonObject:
        return cast(
            JsonObject,
            await self._request("GET", f"/v1/workflow-executions/{execution_id}"),
        )

    async def list_artifacts(self, execution_id: UUID) -> list[Any]:
        return cast(
            list[Any],
            await self._request("GET", f"/v1/workflow-executions/{execution_id}/artifacts"),
        )

    async def approve_workflow_node(self, execution_id: UUID, node_key: str) -> JsonObject:
        return cast(
            JsonObject,
            await self._request(
                "POST", f"/v1/workflow-executions/{execution_id}/approvals/{node_key}"
            ),
        )

    async def cancel_run(self, run_id: UUID) -> JsonObject:
        return cast(JsonObject, await self._request("POST", f"/v1/runs/{run_id}/cancel"))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: JsonObject | None = None,
        params: dict[str, str | int] | None = None,
        headers: dict[str, str] | None = None,
    ) -> JsonPayload:
        if not self._token:
            raise ControlPlaneError("JB_API_TOKEN is required by the MCP server")
        request_headers = {"Authorization": f"Bearer {self._token}"}
        request_headers.update(headers or {})
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                transport=self._transport,
                timeout=self._timeout_seconds,
            ) as client:
                response = await client.request(
                    method, path, json=payload, params=params, headers=request_headers
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = self._error_detail(exc.response)
            raise ControlPlaneError(
                f"control plane rejected the request ({exc.response.status_code}): {detail}"
            ) from None
        except httpx.RequestError as exc:
            raise ControlPlaneError(f"control plane request failed: {exc}") from None
        return cast(JsonPayload, response.json())

    @staticmethod
    def _query(*, status: str | None, limit: int) -> dict[str, str | int]:
        query: dict[str, str | int] = {"limit": limit}
        if status is not None:
            query["status"] = status
        return query

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text or response.reason_phrase
        if isinstance(body, dict):
            detail = body.get("detail")
            if isinstance(detail, str):
                return detail
        return response.reason_phrase
