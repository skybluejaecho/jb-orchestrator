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

ORCH-005 adds the distributed worker runtime:

- atomic READY-node claiming with PostgreSQL `FOR UPDATE SKIP LOCKED`
- expiring worker leases, token validation, heartbeat renewal, and crash recovery
- stable per-node-visit idempotency keys for at-least-once execution
- executor ports for later Codex, Orca, OpenClaw, MCP, or local adapters
- one-shot and continuous polling runtime with timeout and retry handling

ORCH-006 adds installable executor routing:

- immutable task `executor_key`, instructions, and JSON configuration
- worker capability filtering before PostgreSQL task claim
- runtime executor registry with duplicate and contract validation
- adapter discovery through the `jb_orchestrator.executors` Python entry-point group
- worker CLI startup checks and installed-executor listing

ORCH-007 adds the versioned skill catalog:

- immutable local, Git, and archive skill metadata with SHA-256 content identity
- REST registration, latest-version listing, and exact-version lookup
- multiple exact skill references per workflow task node
- resolved skill metadata copied into each workflow execution snapshot and task claim
- explicit separation between skills, executor adapters, and MCP tool servers

ORCH-008 adds verified skill materialization:

- safe local, pinned Git, and size-limited archive source fetchers
- canonical directory SHA-256 verification before executor invocation
- atomic content-addressed cache with verification on every reuse
- configured remote-host allowlists and path, symlink, and archive traversal defenses
- verified skill entrypoint paths delivered through each task claim

ORCH-009 adds deterministic model routing:

- immutable, versioned model profiles with provider, tier, context, price, and capabilities
- explicit complexity, risk, quality, context, capability, and maximum-cost requirements
- fail-closed filtering followed by deterministic cheapest-sufficient model selection
- routing policy version, reasons, and estimated cost pinned in workflow snapshots
- selected provider and model identity delivered to executor task claims

ORCH-010 adds project budget enforcement:

- project-level USD limits with separate reserved, spent, and available balances
- row-locked, idempotent maximum-cost reservations before executor invocation
- append-only actual token usage and conservative unknown-usage forfeiture records
- retry-safe settlement using stable workflow task idempotency keys
- active reservation release when a run or workflow is cancelled

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
uv run jb skill digest skills/my-skill
uv run jb-worker --list-executors
# After installing at least one executor adapter:
uv run jb-worker --once
```

Executor adapter packages expose a no-argument factory in their `pyproject.toml`:

```toml
[project.entry-points."jb_orchestrator.executors"]
codex = "jb_codex_executor:create_executor"
```

The factory returns an object implementing the async `TaskExecutor.execute(claim)` contract.
Its entry-point name must match the workflow node's `executor_key`.
For model-routed tasks, the executor returns provider-reported input and output token usage in
`TaskResult.usage`; configured project budgets require this usage for actual settlement.

Skill registration stores immutable metadata; workers fetch and verify the files only when a
referencing task is claimed. Local sources must be below `JB_SKILL_LOCAL_ROOT`. Remote Git and
archive hosts must be explicitly listed in the JSON array `JB_SKILL_ALLOWED_REMOTE_HOSTS`.
Verified packages are stored below `JB_SKILL_CACHE_DIR`, and executors receive only their
verified entrypoint paths.

The API exposes:

- `GET /health/live`
- `GET /health/ready`
- `POST /v1/projects`
- `POST /v1/projects/{project_id}/requests`
- `GET /v1/requests/{request_id}`
- `GET /v1/runs/{run_id}`
- `POST /v1/runs/{run_id}/approve`
- `POST /v1/runs/{run_id}/cancel`
- `POST /v1/skills`
- `GET /v1/skills`
- `GET /v1/skills/{key}?version={version}`
- `POST /v1/models`
- `GET /v1/models`
- `GET /v1/models/{key}?version={version}`
- `PUT /v1/projects/{project_id}/budget`
- `GET /v1/projects/{project_id}/budget`
- `GET /v1/projects/{project_id}/usage`

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
