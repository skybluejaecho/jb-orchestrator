# jb-orchestrator

`jb-orchestrator` is a local-first orchestration core for reproducible agent workflows.
It stores execution state in PostgreSQL and exposes the same application behavior through
API, worker, CLI, and later MCP adapters.

## Implemented foundations

ORCH-001 established the repository foundation:

- FastAPI application with health endpoints
- worker and administration CLI entry points
- PostgreSQL development service
- lint, type-check, test, and GitHub Actions CI configuration
- modular-monolith package boundaries

ORCH-002 adds the initial durable domain:

- Project, UserRequest, and Run domain entities
- guarded request and run lifecycle transitions
- SQLAlchemy persistence records and repository ports
- Alembic initial PostgreSQL migration
- optimistic concurrency versioning for runs

ORCH-003 exposes the first control-plane use cases:

- transactional SQLAlchemy repositories and Unit of Work
- project registration and request/run REST endpoints
- run approval and cancellation controls
- administration CLI commands backed by the REST API
- durable application events for request and run state changes

ORCH-004 adds the deterministic workflow core:

- validated, versioned workflow graph definitions
- immutable per-run snapshots and durable node execution state
- explicit task, approval, terminal, retry, and bounded repair-loop transitions
- transactional workflow services and append-only transition events
- PostgreSQL migrations and in-memory/SQLAlchemy round-trip tests

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker with Docker Compose

## Setup

```powershell
Copy-Item .env.example .env
uv sync --extra dev
docker compose up -d postgres
uv run alembic upgrade head
```

## Run

```powershell
uv run jb-api
uv run jb doctor
uv run jb-worker --once
```

The API exposes:

- `GET /health/live`
- `GET /health/ready`
- `POST /v1/projects`
- `POST /v1/projects/{project_id}/requests`
- `GET /v1/requests/{request_id}`
- `GET /v1/runs/{run_id}`
- `POST /v1/runs/{run_id}/approve`
- `POST /v1/runs/{run_id}/cancel`

## Quality checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

## Branch strategy

- `main`: production-ready releases
- `develop`: integration branch
- `feature/ORCH-<number>-<description>`: feature work
- `release/<version>`: release stabilization
- `hotfix/ORCH-<number>-<description>`: urgent production fixes

Commits follow Conventional Commits, for example:

```text
feat(workflow): add node state transitions
test(api): cover request lifecycle
docs(adr): record job queue decision
```
