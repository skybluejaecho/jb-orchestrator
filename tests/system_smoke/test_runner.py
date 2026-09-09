from pathlib import Path

import httpx
import pytest

from jb_orchestrator.config import get_settings
from jb_orchestrator.system_smoke import (
    SystemSmokeError,
    _SmokeServiceAccount,
    _verify_credential_rotation,
    _workflow_payload,
    run_system_smoke,
)


def test_system_smoke_fails_closed_outside_test_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JB_ENVIRONMENT", "local")
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemSmokeError, match="JB_ENVIRONMENT=test"):
            run_system_smoke(tmp_path)
    finally:
        get_settings.cache_clear()


def test_smoke_workflow_exercises_worker_and_approval_paths() -> None:
    payload = _workflow_payload("system-smoke-test")

    assert payload["entry_node"] == "work"
    assert payload["nodes"][0]["executor_key"] == "system-smoke"
    assert {edge["outcome"] for edge in payload["edges"]} == {
        "success",
        "failure",
        "approved",
        "rejected",
    }


def test_credential_rotation_smoke_verifies_authentication_revocation_and_audit() -> None:
    account_id = "00000000-0000-0000-0000-000000000001"
    original_id = "00000000-0000-0000-0000-000000000002"
    replacement_id = "00000000-0000-0000-0000-000000000003"

    def handler(request: httpx.Request) -> httpx.Response:
        authorization = request.headers.get("Authorization")
        if request.method == "POST":
            return httpx.Response(
                201,
                json={"id": replacement_id, "token": "replacement-token"},
            )
        if request.method == "DELETE":
            return httpx.Response(
                200,
                json={"credential_id": original_id, "revoked": True},
            )
        if request.url.path == "/v1/projects":
            if authorization == "Bearer original-token":
                return httpx.Response(401, json={"detail": "revoked"})
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/credentials"):
            return httpx.Response(
                200,
                json=[
                    {"id": replacement_id, "active": True},
                    {"id": original_id, "active": False},
                ],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "event_type": "service_account.credential_revoked",
                    "credential_id": original_id,
                    "actor_credential_id": replacement_id,
                },
                {
                    "event_type": "service_account.credential_issued",
                    "credential_id": replacement_id,
                    "actor_credential_id": original_id,
                },
                {"event_type": "service_account.credential_issued"},
            ],
        )

    with httpx.Client(
        base_url="http://control-plane.local",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = _verify_credential_rotation(
            client,
            _SmokeServiceAccount(account_id, original_id, "original-token"),
        )

    assert result == replacement_id


def test_credential_rotation_smoke_fails_when_revoked_token_remains_valid() -> None:
    identity = _SmokeServiceAccount(
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        "original-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                201,
                json={
                    "id": "00000000-0000-0000-0000-000000000003",
                    "token": "replacement-token",
                },
            )
        if request.method == "DELETE":
            return httpx.Response(
                200,
                json={"credential_id": identity.credential_id, "revoked": True},
            )
        return httpx.Response(200, json=[])

    with (
        httpx.Client(
            base_url="http://control-plane.local",
            transport=httpx.MockTransport(handler),
        ) as client,
        pytest.raises(SystemSmokeError, match="remained usable"),
    ):
        _verify_credential_rotation(client, identity)
