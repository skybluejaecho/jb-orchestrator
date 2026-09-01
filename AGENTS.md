# Repository instructions

## Architecture

- Keep the system a modular monolith until measured constraints justify extraction.
- PostgreSQL is the source of truth for orchestration state.
- API, CLI, worker, and MCP adapters must call application services rather than duplicate rules.
- Keep agent runtimes and external clients behind explicit ports/adapters.
- Persist decisions and outputs as structured records or artifacts; do not depend on chat memory.

## Development

- Use Python 3.12 and `uv`.
- Add type annotations to production code.
- Add or update tests for behavioral changes.
- Run Ruff, mypy, and pytest before considering a task complete.
- Do not push, merge, or change remotes without explicit user approval.

## Git

- Branch from `develop` using `feature/ORCH-<number>-<description>`.
- Use Conventional Commits.
- Keep commits focused on one logical change.

