"""Worker process entry point."""

import typer

app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback()
def run(
    *,
    once: bool = typer.Option(False, help="Poll once and exit."),
) -> None:
    """Start the worker scaffold."""

    mode = "once" if once else "continuous"
    typer.echo(f"jb-orchestrator worker scaffold ready (mode={mode})")


def main() -> None:
    """Invoke the worker application."""

    app()


if __name__ == "__main__":
    main()
