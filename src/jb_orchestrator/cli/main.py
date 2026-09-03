"""Administration CLI entry point."""

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID

import httpx
import typer

from jb_orchestrator import __version__
from jb_orchestrator.application import SecurityService
from jb_orchestrator.config import get_settings
from jb_orchestrator.infrastructure.database import SqlAlchemyUnitOfWork, create_session_factory
from jb_orchestrator.security import ApiPermission
from jb_orchestrator.skills.materialization import (
    SkillMaterializationError,
    compute_directory_digest,
)

app = typer.Typer(no_args_is_help=True, help="Administer jb-orchestrator.")
project_app = typer.Typer(no_args_is_help=True, help="Manage registered projects.")
request_app = typer.Typer(no_args_is_help=True, help="Submit and inspect user requests.")
run_app = typer.Typer(no_args_is_help=True, help="Inspect and control runs.")
skill_app = typer.Typer(no_args_is_help=True, help="Inspect and prepare skills.")
auth_app = typer.Typer(no_args_is_help=True, help="Manage API service accounts.")
app.add_typer(project_app, name="project")
app.add_typer(request_app, name="request")
app.add_typer(run_app, name="run")
app.add_typer(skill_app, name="skill")
app.add_typer(auth_app, name="auth")


def call_api(method: str, path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call the configured control-plane API and render failures consistently."""

    settings = get_settings()
    base_url = settings.control_plane_url.rstrip("/")
    headers = {}
    if settings.api_token is not None:
        headers["Authorization"] = f"Bearer {settings.api_token.get_secret_value()}"
    try:
        response = httpx.request(
            method, f"{base_url}{path}", json=payload, headers=headers, timeout=10.0
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        typer.echo(exc.response.text, err=True)
        raise typer.Exit(code=1) from exc
    except httpx.RequestError as exc:
        typer.echo(f"control-plane request failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    return cast(dict[str, Any], response.json())


def echo_json(payload: dict[str, Any]) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


@app.command()
def version() -> None:
    """Print the installed application version."""

    typer.echo(__version__)


@app.command()
def doctor() -> None:
    """Print local configuration diagnostics without exposing secrets."""

    settings = get_settings()
    result = {
        "api": f"{settings.api_host}:{settings.api_port}",
        "api_auth_enabled": settings.api_auth_enabled,
        "api_token_configured": settings.api_token is not None,
        "database_configured": bool(settings.database_url),
        "environment": settings.environment,
        "control_plane_url": settings.control_plane_url,
        "service": "jb-orchestrator",
        "version": __version__,
    }
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


def security_service() -> SecurityService:
    session_factory = create_session_factory()
    return SecurityService(lambda: SqlAlchemyUnitOfWork(session_factory))


@auth_app.command("issue")
def issue_service_account(
    *,
    key: Annotated[str, typer.Option(help="Stable service-account key.")],
    name: Annotated[str, typer.Option(help="Human-readable service-account name.")],
    permission: Annotated[
        list[ApiPermission], typer.Option(help="Permission to grant; repeat as needed.")
    ],
    project_id: Annotated[
        list[UUID] | None, typer.Option(help="Project scope; repeat as needed.")
    ] = None,
    all_projects: Annotated[bool, typer.Option(help="Grant access to every project.")] = False,
) -> None:
    """Issue a service-account bearer token and print it once."""

    issued = asyncio.run(
        security_service().issue(
            key=key,
            name=name,
            permissions=permission,
            project_ids=project_id or (),
            all_projects=all_projects,
        )
    )
    echo_json(
        {
            "account_id": str(issued.account.id),
            "key": issued.account.key,
            "token": issued.token,
            "warning": "Store this token now; it cannot be retrieved later.",
        }
    )


@auth_app.command("revoke")
def revoke_service_account(account_id: UUID) -> None:
    """Revoke a service account immediately."""

    asyncio.run(security_service().revoke(account_id))
    echo_json({"account_id": str(account_id), "revoked": True})


@skill_app.command("digest")
def digest_skill(path: Path) -> None:
    """Compute the canonical SHA-256 identity of a local skill directory."""

    try:
        typer.echo(compute_directory_digest(path))
    except (FileNotFoundError, NotADirectoryError, SkillMaterializationError) as exc:
        typer.echo(f"cannot digest skill: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@project_app.command("register")
def register_project(
    *,
    key: Annotated[str, typer.Option(help="Stable lowercase project key.")],
    name: Annotated[str, typer.Option(help="Human-readable project name.")],
    repository_url: Annotated[str, typer.Option(help="Git repository URL.")],
    default_branch: Annotated[str, typer.Option(help="Repository default branch.")] = "main",
) -> None:
    """Register a source repository."""

    echo_json(
        call_api(
            "POST",
            "/v1/projects",
            payload={
                "key": key,
                "name": name,
                "repository_url": repository_url,
                "default_branch": default_branch,
            },
        )
    )


@request_app.command("create")
def create_request(
    *,
    project_id: Annotated[UUID, typer.Option(help="Registered project UUID.")],
    prompt: Annotated[str, typer.Option(help="Original user request.")],
    title: Annotated[str | None, typer.Option(help="Optional request title.")] = None,
) -> None:
    """Create a user request and its first queued run."""

    echo_json(
        call_api(
            "POST",
            f"/v1/projects/{project_id}/requests",
            payload={"prompt": prompt, "title": title},
        )
    )


@request_app.command("get")
def get_request(request_id: UUID) -> None:
    """Read one user request."""

    echo_json(call_api("GET", f"/v1/requests/{request_id}"))


@run_app.command("get")
def get_run(run_id: UUID) -> None:
    """Read one run."""

    echo_json(call_api("GET", f"/v1/runs/{run_id}"))


@run_app.command("approve")
def approve_run(run_id: UUID) -> None:
    """Approve a run currently waiting for approval."""

    echo_json(call_api("POST", f"/v1/runs/{run_id}/approve"))


@run_app.command("cancel")
def cancel_run(run_id: UUID) -> None:
    """Cancel an active run and its user request."""

    echo_json(call_api("POST", f"/v1/runs/{run_id}/cancel"))


def main() -> None:
    """Invoke the CLI application."""

    app()


if __name__ == "__main__":
    main()
