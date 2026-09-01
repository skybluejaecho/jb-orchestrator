"""Administration CLI entry point."""

import json

import typer

from jb_orchestrator import __version__
from jb_orchestrator.config import get_settings

app = typer.Typer(no_args_is_help=True, help="Administer jb-orchestrator.")


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
        "database_configured": bool(settings.database_url),
        "environment": settings.environment,
        "service": "jb-orchestrator",
        "version": __version__,
    }
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


def main() -> None:
    """Invoke the CLI application."""

    app()


if __name__ == "__main__":
    main()
