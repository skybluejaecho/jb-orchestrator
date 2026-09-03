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

ORCH-011 exposes the workflow control plane:

- versioned workflow definition registration, latest-version listing, and exact lookup
- workflow execution startup for an existing run with an immutable definition snapshot
- workflow and node execution status queries by run or execution identifier
- explicit approval resolution and workflow cancellation endpoints
- domain validation errors returned as structured HTTP problem details

ORCH-012 hardens long-running worker execution:

- periodic PostgreSQL lease renewal while an executor is active
- fail-closed cancellation when heartbeat ownership can no longer be renewed
- bounded timeout and graceful worker-stop cleanup
- optional idempotent provider-side cancellation hooks for remote agent runtimes
- configurable heartbeat and cancellation timeout settings

ORCH-013 validates the OpenClaw Gateway boundary before production integration:

- exact-pinned official Gateway client and protocol packages in an isolated Node.js spike
- protocol-validated `agent` and `agent.wait` execution using stable JB idempotency keys
- exact-run cancellation through `sessions.abort` and same-session continuation semantics
- documented PostgreSQL-to-OpenClaw ownership boundary and production adapter follow-up

See `tools/openclaw-gateway-spike/README.md` for the executable contract test and live Gateway
instructions. Live validation requires an independently configured OpenClaw Gateway and is not a
prerequisite for the Python application runtime.

ORCH-014 adds the first installable OpenClaw executor adapter:

- PostgreSQL ledger mapping stable JB task keys to OpenClaw sessions and runs
- crash-safe resume without duplicate `agent` calls and persisted terminal projections
- bounded JSON subprocess bridge that keeps credentials and prompts out of process arguments
- exact-run provider cancellation integrated with the ORCH-012 worker lifecycle
- separately installed `openclaw` executor entry point, leaving the core runtime optional

See `adapters/openclaw/README.md` for installation and current production-hardening requirements.

ORCH-015 hardens OpenClaw Gateway authentication:

- persistent Ed25519 worker identity with challenge-bound signatures
- shared credentials used only for initial device pairing bootstrap
- role-scoped Gateway device-token persistence, rotation, and clearing
- atomic private state writes outside PostgreSQL and process arguments
- optional TLS certificate fingerprint pinning for remote `wss://` Gateways

ORCH-016 exposes durable external execution observation:

- PostgreSQL-backed external execution detail and filtered list APIs
- idempotent prepared, accepted, and terminal external execution events
- polling-friendly status projections for Jarvis and other clients

ORCH-017 adds a resumable external execution event stream:

- database-issued monotonic event sequences for deterministic replay order
- SSE delivery with durable event IDs, idle heartbeats, and proxy buffering disabled
- reconnection through the standard `Last-Event-ID` header or an initial `after` cursor
- ledger replay before live polling so temporary client disconnects do not lose events

ORCH-018 adds durable task context and artifacts:

- original request and repository identity pinned in each workflow snapshot
- immutable JSON artifacts stored for every completed task node visit
- only the latest artifacts from direct predecessor nodes delivered in each task claim
- structured request, project, artifact, and verified-skill context rendered for OpenClaw
- workflow artifact history exposed through the control-plane API

ORCH-019 adds composable, versioned phase packs:

- reusable phase roles, instructions, skill references, and JSON output contracts
- named required or optional phase inputs independent of a workflow graph
- explicit workflow-node mappings from input names to producer-node artifacts
- exact phase-pack versions pinned into each workflow execution snapshot
- named inputs and output contracts rendered for OpenClaw execution
- legacy nodes retaining automatic direct-predecessor artifact delivery

ORCH-020 enforces phase output contracts:

- phase output contracts validated as JSON Schema Draft 2020-12
- malformed schemas rejected before a phase-pack version is registered
- invalid successful outputs converted into structured failure artifacts
- original rejected output and deterministic validation details retained for repair
- contract failures routed through ordinary workflow failure edges and repair loops
- valid successes and explicit executor failures preserved without rewriting

ORCH-021 adds deterministic parallel workflow regions:

- explicit non-executing fork and all-source join control nodes
- multiple branch tasks becoming READY for concurrent workers
- join activation only after every direct predecessor has completed
- workflow-aggregate row locking around short claim and transition transactions
- sibling task cancellation when a parallel path terminates or fails the workflow
- named Phase Pack inputs combining durable artifacts from independent branches

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
- `POST /v1/workflows`
- `GET /v1/workflows`
- `GET /v1/workflows/{key}?version={version}`
- `POST /v1/runs/{run_id}/workflow`
- `GET /v1/runs/{run_id}/workflow`
- `GET /v1/workflow-executions/{execution_id}`
- `GET /v1/workflow-executions/{execution_id}/artifacts`
- `POST /v1/workflow-executions/{execution_id}/approvals/{node_key}`
- `POST /v1/workflow-executions/{execution_id}/cancel`
- `GET /v1/external-executions`
- `GET /v1/external-executions/events/stream`
- `GET /v1/external-executions/{execution_id}`

외부 런타임 실행은 PostgreSQL 원장을 기준으로 조회합니다. 목록 API는
`workflow_execution_id`, `run_id`, `status`, `limit` 필터를 지원하므로 Jarvis 같은
클라이언트가 폴링으로 현재 상태를 표시할 수 있습니다. 각 상태 전이는 동일 트랜잭션에서
작은 도메인 이벤트도 기록합니다. SSE 엔드포인트는 저장된 이벤트를 먼저 재생한 뒤 새
이벤트를 전달하며, 재연결 시 `Last-Event-ID` 이후부터 이어서 받을 수 있습니다.

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
