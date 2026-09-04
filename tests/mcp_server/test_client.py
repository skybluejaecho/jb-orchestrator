from typing import Any
from uuid import uuid4

import httpx
import pytest

from jb_orchestrator.mcp_server import ControlPlaneClient, ControlPlaneError


async def test_dispatch_uses_mcp_origin_authentication_and_idempotency() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={"replayed": False})

    project_id = uuid4()
    client = ControlPlaneClient(
        base_url="http://control.test",
        token="secret",
        transport=httpx.MockTransport(handler),
    )

    result = await client.dispatch_request(
        project_id,
        prompt="Build it",
        title="Implementation",
        idempotency_key="openclaw-message-42",
        actor_id="user-1",
        conversation_id="session-9",
        definition_key="planning-only",
        definition_version=2,
    )

    request: httpx.Request = captured["request"]
    assert request.url.path == f"/v1/projects/{project_id}/dispatches"
    assert request.headers["authorization"] == "Bearer secret"
    assert request.headers["idempotency-key"] == "openclaw-message-42"
    assert request.headers["x-jb-ingress-key"] == "mcp"
    assert request.headers["x-jb-actor-id"] == "user-1"
    assert request.headers["x-jb-conversation-id"] == "session-9"
    assert request.read().decode() == (
        '{"prompt":"Build it","title":"Implementation","workflow":'
        '{"definition_key":"planning-only","definition_version":2}}'
    )
    assert result == {"replayed": False}


async def test_dispatch_rejects_partial_workflow_override_before_network() -> None:
    client = ControlPlaneClient(base_url="http://control.test", token="secret")

    with pytest.raises(ControlPlaneError, match="requires definition_key and definition_version"):
        await client.dispatch_request(
            uuid4(),
            prompt="Build it",
            idempotency_key="partial",
            definition_key="planning-only",
        )


async def test_missing_token_fails_before_network_request() -> None:
    client = ControlPlaneClient(base_url="http://control.test", token=None)

    with pytest.raises(ControlPlaneError, match="JB_API_TOKEN"):
        await client.get_project(uuid4())


async def test_api_error_exposes_safe_problem_detail_without_token() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "project scope denied"})

    client = ControlPlaneClient(
        base_url="http://control.test",
        token="do-not-leak",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ControlPlaneError, match=r"403.*project scope denied") as error:
        await client.get_project(uuid4())
    assert "do-not-leak" not in str(error.value)
